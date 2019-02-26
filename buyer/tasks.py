from celery import shared_task
from celery.utils.log import get_task_logger
from requests.adapters import ConnectionError
from re import sub
from config import constants
from pairs.models import Order
from pairs.parsers import get_my_price_from_response, get_ebay_price_from_response, get_ebay_quantity_from_response
from utils import secret_dict, amazon_products_api, ebay_trading_api
from .interface import SeleniumBuyer, PurchaseStoppedException

logger = get_task_logger(__name__)


@shared_task(name='Make purchases')
def make_purchases():
    """ Make automated purchases for unprocessed orders """

    orders = Order.objects.filter(all_set=False)

    if not len(orders):
        logger.info('No orders to make purchases')
        return

    # initialize selenium buyer

    eb_credentials = (secret_dict['eb_username'], secret_dict['eb_password'])
    pp_credentials = (secret_dict['pp_email'], secret_dict['pp_password'])

    try:
        buyer = SeleniumBuyer(eb_credentials, pp_credentials)

    except (PurchaseStoppedException, ValueError) as e:
        logger.critical('Buyer init failed: {0}'.format(e))
        return

    # make purchases

    for order in orders:
        items_prices = None
        ebay_price, total_profit = 0, 0
        order.items_buying_status, profits = {}, {}

        # preparations

        item_number = 0
        shipping_info = process_shipping_data(order.shipping_info)
        order_items = order.get_items()

        if len(order_items) > 1:
            items_prices = get_order_items_prices([item.asin for item in order_items])

            if not len(items_prices):
                logger.critical('Getting items prices failed, for order: {0}. Aborting.'.format(order.order_id))
                return

        for item in order_items:
            ebay_item_price = 0
            order.items_buying_status[str(item.id)] = {}

            if order.items_counts[str(item.id)] > item.quantity:
                order.items_buying_status[str(item.id)] = False

                logger.critical(
                    'Too high quantity: {0}, for item: {1}'.format(order.items_counts[str(item.id)], item.id)
                )

                item_number += 1
                continue

            ebay_ids = item.ebay_ids.split(';')

            if len(ebay_ids) > 1:
                buying_condition = build_purchase_condition(ebay_ids, order.items_counts[str(item.id)])

                if not len(buying_condition):
                    logger.critical('Building buying condition failed, for item: {0}. Aborting.'.format(item.asin))
                    order.items_buying_status[str(item.id)] = False
                    item_number += 1
                    continue
            else:
                buying_condition = {item.ebay_ids: order.items_counts[str(item.id)]}

            all_ids_failed = True

            for ebay_id in buying_condition:
                shipping_info['count'] = str(buying_condition[ebay_id])

                try:
                    total = buyer.purchase(ebay_id, ship_info=shipping_info)

                except PurchaseStoppedException as e:
                    order.items_buying_status[str(item.id)][ebay_id] = False
                    logger.critical('Stopped by: {0}, for id: {1}'.format(e, ebay_id))
                    continue

                all_ids_failed = False
                ebay_item_price += total

                # set purchase status

                if not total:
                    order.items_buying_status[str(item.id)][ebay_id] = False
                    logger.warning('Zero total price for id: {0}'.format(ebay_id))
                else:
                    order.items_buying_status[str(item.id)][ebay_id] = True

            ebay_price += ebay_item_price

            if all_ids_failed:
                item_number += 1
                continue

            # calculate profits

            if len(order_items) == 1:
                # in one item case

                income = order.amazon_price * constants.profit_percentage - ebay_item_price
                total_profit += income
                profits[item.owner.username] = item.owner.get_profit(income)
                item.owner.update_profit(income)

            else:
                # in multiple items case

                if items_prices[item_number]:
                    income = items_prices[item_number] * constants.profit_percentage - ebay_item_price
                    total_profit += income

                    if item.owner.username in profits:
                        profits[item.owner.username] += item.owner.get_profit(income)
                    else:
                        profits[item.owner.username] = item.owner.get_profit(income)

                    item.owner.update_profit(income)

                else:
                    logger.warning('Zero Amazon price for item: {0}'.format(item.asin))

            item_number += 1

        order.all_set = True
        order.ebay_price = ebay_price
        order.total_profit = total_profit
        order.save(update_fields=['all_set', 'items_buying_status', 'ebay_price', 'total_profit'])
        order.set_profits(profits)

        logger.info('Order {0} processed'.format(order.order_id))

    logger.info('Purchases complete')


def process_shipping_data(shipping_info):
    """ Check order shipping data before purchase """

    if ' ' not in shipping_info['Name']:
        shipping_info['first_name'] = shipping_info['Name']
        shipping_info['last_name'] = ''

    else:
        shipping_info['first_name'] = shipping_info['Name'][:shipping_info['Name'].find(' ')]
        shipping_info['last_name'] = shipping_info['Name'][shipping_info['Name'].find(' ') + 1:]

    shipping_info['Phone'] = sub('[^0-9]', '', shipping_info['Phone'])

    if len(shipping_info['StateOrRegion']) == 2:
        try:
            shipping_info['StateOrRegion'] = constants.us_states_abbr[shipping_info['StateOrRegion'].upper()]

        except KeyError:
            pass

    else:
        region = shipping_info['StateOrRegion'][0].upper() + shipping_info['StateOrRegion'][1:].lower()
        shipping_info['StateOrRegion'] = region

    return shipping_info


def build_purchase_condition(ebay_ids, total_quantity):
    """ Choose best purchase condition by price and quantity """

    ebay_ids_prices, ebay_ids_counts = {}, {}

    for ebay_id in ebay_ids:
        try:
            response = ebay_trading_api.api.execute('GetItem', {'ItemID': ebay_id})

        except ConnectionError:
            logger.critical('Remote end closed connection, id: {0}'.format(ebay_id))
            break

        except ebay_trading_api.connection_error as e:
            logger.critical('eBay api unhandled error: {0}.'.format(e.response.dict()['Errors']))
            break

        ebay_ids_prices[ebay_id] = get_ebay_price_from_response(response)
        ebay_ids_counts[ebay_id] = get_ebay_quantity_from_response(response)

    buying_info = {}
    ebay_ids_prices = sorted(ebay_ids_prices.items(), key=lambda x: (x[1], x[0]))

    if not len(ebay_ids_prices):
        return {}

    for ebay_id_price in ebay_ids_prices:
        if total_quantity <= ebay_ids_counts[ebay_id_price[0]]:
            buying_info[ebay_id_price[0]] = total_quantity
            break

        buying_info[ebay_id_price[0]] = ebay_ids_counts[ebay_id_price[0]]
        total_quantity -= ebay_ids_counts[ebay_id_price[0]]

    return buying_info


def get_order_items_prices(asins, max_asins=constants.amazon_get_my_price_items_limit):
    """ Get my Amazon items prices for given asins """

    items_prices = []
    asins = [asins[x:x + max_asins] for x in range(0, len(asins), max_asins)]

    for part in asins:
        try:
            response = amazon_products_api.api.get_my_price_for_asin(amazon_products_api.region, part)

        except amazon_products_api.connection_error as e:
            logger.critical('Unhandled Amazon api error: {0}'.format(e))
            return []

        items_prices += get_my_price_from_response(response)

    return items_prices
