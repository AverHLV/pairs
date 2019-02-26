from django.utils.timezone import get_current_timezone
from django.core.exceptions import ObjectDoesNotExist
from celery import shared_task
from celery.utils.log import get_task_logger
from requests.adapters import ConnectionError
from datetime import datetime, timedelta
from time import sleep
from uuid import uuid4
from re import sub
from config import constants
from selenium_buyer.interface import SeleniumBuyer, PurchaseStoppedException
from .models import Pair, Order, shipping_info_fields

from .parsers import (
    get_price_from_response, get_my_price_from_response, get_ebay_price_from_response, get_ebay_quantity_from_response
)

from utils import (
    secret_dict,
    ebay_trading_api,                                                                     # eBay apis
    amazon_products_api, amazon_orders_api, amazon_feeds_api,                             # Amazon apis
    xml_quantity_helper, xml_product_helper, xml_price_helper, xml_delete_product_helper  # xml helpers
)

logger = get_task_logger(__name__)


def gen_sku(length=10):
    """ Generate unique seller sku string in format XX-XXXX-XXXX... """

    if length < 10:
        raise ValueError('SKU length must be greater than 9')

    while True:
        sku = uuid4().hex[:length].upper()
        sku = sku[:2] + '-' + sku[2:6] + '-' + sku[6:]

        if not Pair.objects.filter(seller_sku=sku).exists():
            return sku


def check_products(check_type, asins=None, max_asins=constants.amazon_get_my_price_items_limit,
                   after_delay=constants.check_after_delay):
    """
    Check for seller sku in Amazon inventory

    :param asins: list with ASINs for check in check_after case
    :param max_asins: max items per request for GetMyPriceForASIN request
    :param after_delay: delay for Amazon to process old requests
    :param check_type:
        check_before - for checking products existence before uploading
        check_after - check uploading results
    """

    if check_type == 'check_before':
        asins = [pair.asin for pair in Pair.objects.filter(seller_sku='')]

    elif check_type == 'check_after' and asins is None:
        raise ValueError('ASINs list is None')

    elif check_type not in ('check_before', 'check_after'):
        raise ValueError('Wrong check type: {0}'.format(check_type))

    asins = [asins[x:x + max_asins] for x in range(0, len(asins), max_asins)]

    if not len(asins):
        logger.info('No pairs to check, check_type: {0}'.format(check_type))
        return

    if check_type == 'check_after':
        sleep(after_delay)

    for part in asins:
        try:
            response = amazon_products_api.api.get_my_price_for_asin(amazon_products_api.region, part)

        except amazon_products_api.connection_error as e:
            logger.critical('Unhandled Amazon api error: {0}'.format(e))
            continue

        if len(part) == 1:
            # in one item case

            pair = Pair.objects.get(asin=part[0])

            try:
                pair.seller_sku = response.parsed['Product']['Offers']['Offer']['SellerSKU']['value']

            except KeyError:
                if check_type == 'check_after':
                    pair.seller_sku = ''
                    pair.checked = 4
                    pair.save(update_fields=['seller_sku', 'checked'])

                    pair.owner.pairs_count -= 1
                    pair.owner.save(update_fields=['pairs_count'])

            else:
                if check_type == 'check_before':
                    pair.save(update_fields=['seller_sku'])

        else:
            # in multiple items case

            for i in range(len(response.parsed)):
                pair = Pair.objects.get(asin=part[i])

                try:
                    pair.seller_sku = response.parsed[i]['Product']['Offers']['Offer']['SellerSKU']['value']

                except KeyError:
                    if check_type == 'check_after':
                        pair.seller_sku = ''
                        pair.checked = 4
                        pair.save(update_fields=['seller_sku', 'checked'])

                        pair.owner.pairs_count -= 1
                        pair.owner.save(update_fields=['pairs_count'])

                else:
                    if check_type == 'check_before':
                        pair.save(update_fields=['seller_sku'])

    if check_type == 'check_before':
        logger.info('Checking for existing pairs in inventory complete')
    else:
        logger.info('Checking for upload results complete')


def upload_new_pairs():
    """
    Generate seller_sku for all pairs with this blank field
    and upload them to Amazon
    """

    messages = []

    # gather all pairs with blank seller_sku

    for pair in Pair.objects.filter(seller_sku='').filter(checked=1):
        pair.seller_sku = gen_sku()
        pair.save(update_fields=['seller_sku'])
        messages.append((pair.seller_sku, pair.asin))

    if len(messages):
        xml_product_helper.make_body(messages)
    else:
        logger.warning('No messages to upload products in Amazon.')
        return []

    # upload products to Amazon inventory

    try:
        response = amazon_feeds_api.api.submit_feed(feed=xml_product_helper.tree,
                                                    feed_type=amazon_feeds_api.feed_types['product'],
                                                    marketplaceids=[amazon_feeds_api.region])

    except amazon_feeds_api.connection_error as e:
        xml_product_helper.reload_tree()
        raise ValueError('Unhandled Amazon Feeds api error: {0}.'.format(e))

    xml_product_helper.reload_tree()

    if response.parsed['FeedSubmissionInfo']['FeedProcessingStatus']['value'] != '_SUBMITTED_':
        raise ValueError('Feeds Api did not accept messages to upload products. Status: {0}. Messages: {1}.'
                         .format(response.parsed['FeedSubmissionInfo']['FeedProcessingStatus']['value'], messages))

    logger.info('Products upload complete.')

    # asins for checking results

    return [message[1] for message in messages]


def update_pairs_quantity():
    """
    Update the number of pairs in the database using eBay api,
    then update the number in the Amazon inventory
    """

    messages = []

    # update quantities in db from eBay

    for pair in Pair.objects.all().exclude(checked=4):
        pair.check_quantity()
        pair.save(update_fields=['quantity'])

        if len(pair.seller_sku) and pair.quantity is not None:
            quantity = pair.quantity

            if quantity > 10:
                quantity = 10

            messages.append((pair.seller_sku, quantity))

    if len(messages):
        xml_quantity_helper.make_body(messages)
    else:
        logger.warning('No messages to update quantity in Amazon.')
        return

    # update quantities in Amazon inventory

    try:
        response = amazon_feeds_api.api.submit_feed(feed=xml_quantity_helper.tree,
                                                    feed_type=amazon_feeds_api.feed_types['quantity'],
                                                    marketplaceids=[amazon_feeds_api.region])

    except amazon_feeds_api.connection_error as e:
        xml_quantity_helper.reload_tree()
        raise ValueError('Unhandled Amazon Feeds api error: {0}.'.format(e))

    xml_quantity_helper.reload_tree()

    if response.parsed['FeedSubmissionInfo']['FeedProcessingStatus']['value'] != '_SUBMITTED_':
        raise ValueError('Feeds Api did not accept messages to update quantities. Status: {0}. Messages: {1}.'
                         .format(response.parsed['FeedSubmissionInfo']['FeedProcessingStatus']['value'], messages))

    logger.info('Pairs quantity update complete.')


def get_prices(asins, delay=0.5):
    """ Get BuyBox or lowest listing prices for all asins with delay request period """

    prices = []

    for asin in asins:
        try:
            response = amazon_products_api.api.get_lowest_priced_offers_for_asin(amazon_products_api.region, asin)

        except amazon_products_api.connection_error as e:
            logger.critical('Unhandled Amazon Feeds api error: {0}, for asin: {1}'.format(e, asin))
            continue

        else:
            price = get_price_from_response(response)

            if not price:
                pair = Pair.objects.get(asin=asin)
                price = pair.amazon_approximate_price

            prices.append((asin, price))

        sleep(delay)

    logger.info('Lowest prices received.')
    return prices


def set_prices(asins_prices):
    """ Set correct prices by given asins and price values """

    messages = [(Pair.objects.get(asin=asin[0]).seller_sku, asin[1]) for asin in asins_prices]

    if len(messages):
        xml_price_helper.make_body(messages)
    else:
        logger.warning('No messages to set price in Amazon.')
        return

    try:
        response = amazon_feeds_api.api.submit_feed(feed=xml_price_helper.tree,
                                                    feed_type=amazon_feeds_api.feed_types['price'],
                                                    marketplaceids=[amazon_feeds_api.region])

    except amazon_feeds_api.connection_error as e:
        xml_price_helper.reload_tree()
        raise ValueError('Unhandled Amazon Feeds api error: {0}.'.format(e))

    xml_price_helper.reload_tree()

    if response.parsed['FeedSubmissionInfo']['FeedProcessingStatus']['value'] != '_SUBMITTED_':
        raise ValueError('Feeds Api did not accept messages to set prices. Status: {0}. Messages: {1}.'
                         .format(response.parsed['FeedSubmissionInfo']['FeedProcessingStatus']['value'], messages))

    logger.info('Prices are set')


def set_prices_local(asins_prices):
    """ Set Amazon approximate prices in db """

    for message in asins_prices:
        pair = Pair.objects.get(asin=message[0])
        pair.amazon_approximate_price = message[1]
        pair.save(update_fields=['amazon_approximate_price'])


def calc_app_price(input_ebay_prices):
    """ Calculate Amazon approximate price """

    prices, ebay_prices = [], []

    for ebay_price in input_ebay_prices:
        if not ebay_price:
            continue

        for interval in constants.profit_intervals:
            if interval[0] <= ebay_price < interval[1]:
                price = ebay_price * constants.profit_intervals[interval] / constants.profit_percentage
                prices.append(price)
                ebay_prices.append(ebay_price)
                break

    # getting approximate price

    if not len(prices):
        print(input_ebay_prices)
        return 0

    max_ebay_price_coeff = 0
    max_price = max(prices)
    max_ebay_price = ebay_prices[prices.index(max_price)]

    for interval in constants.amazon_approximate_price_percent:
        if interval[0] <= max_ebay_price < interval[1]:
            max_ebay_price_coeff = constants.amazon_approximate_price_percent[interval]

    return round(max_price + max_ebay_price * max_ebay_price_coeff, 2)


def empty_app_prices():
    """ Populate empty approximate Amazon prices in db """

    asins_prices = []
    ebay_ids = [(pair.asin, pair.ebay_ids.split(';')) for pair in Pair.objects.all()
                if not pair.amazon_approximate_price]

    for pair_info in ebay_ids:
        ebay_price = []

        for ebay_id in pair_info[1]:
            response = ebay_trading_api.api.execute('GetItem', {'ItemID': ebay_id})
            ebay_price.append(get_ebay_price_from_response(response))

        ebay_price_set = set(ebay_price)

        if len(ebay_price_set) == 1 and not list(ebay_price_set)[0]:
            print(pair_info[0])

        else:
            app_price = calc_app_price(ebay_price)

            if not app_price:
                print(pair_info[0])

            asins_prices.append((pair_info[0], app_price))

    set_prices_local(asins_prices)
    print('Done')


def feed_cycle(tries, delay, failure_message, func, *args, for_upload=False):
    """ Amazon SubmitFeed failure handler """

    asins = []

    while tries:
        try:
            if for_upload:
                asins = func(*args)
            else:
                func(*args)

            break

        except ValueError:
            sleep(delay // 2)
            tries -= 1

    if not tries:
        raise WorkflowError(failure_message, 300)

    return asins


def check_feed_done(delay=60, max_cycle_count=90):
    """ Check until the feeds request is completed """

    def check_result():
        try:
            response = amazon_feeds_api.api.get_feed_submission_list(max_count='1')

        except amazon_feeds_api.connection_error as e:
            logger.critical('Unhandled Amazon Feeds api error: {0}.'.format(e))
            return False

        if response.parsed['FeedSubmissionInfo']['FeedProcessingStatus']['value'] == '_DONE_':
            return True

        return False

    i_count = 0

    while True:
        if check_result():
            break

        i_count += 1

        if i_count > max_cycle_count:
            raise WorkflowError('Feed submission processing is out of time', 200)

        sleep(delay)


@shared_task(name='Amazon workflow')
def amazon_update(delay=constants.amazon_workflow_delay, get_price_delay=constants.amazon_get_price_delay, tries=3):
    """
    Amazon items update workflow

    :param delay: sleep period in seconds between workflow operations
    :param get_price_delay: maximum GetMyPriceForASIN requests per hour
    :param tries: number of tries in SubmitFeed failure case
    """

    asins = []
    logger.info('Amazon workflow starts')

    if tries <= 0:
        raise ValueError('Tries value must be positive')

    try:
        # check for already existing products

        check_products(check_type='check_before')

        # upload new products

        asins = feed_cycle(tries, delay, 'Workflow failed on pairs uploading', upload_new_pairs, for_upload=True)

        if len(asins):
            sleep(delay)
            check_feed_done()

        # update quantities

        feed_cycle(tries, delay, 'Workflow failed on quantity updating', update_pairs_quantity)

        if not len(asins):
            logger.info('Empty asins list before getting prices')
            return

        sleep(delay)
        check_feed_done()

        # get prices from Amazon

        if len(asins) > constants.amazon_get_price_limit:
            prices = []
            parts = [asins[x:x + constants.amazon_get_price_limit] for x in range(0, len(asins),
                                                                                  constants.amazon_get_price_limit)]

            for part in parts:
                prices += get_prices(part)
                sleep(get_price_delay)

        else:
            prices = get_prices(asins)

        # set prices by uploaded asins

        feed_cycle(tries, delay, 'Workflow failed on setting prices', set_prices, prices)

        if not len(prices):
            logger.info('Amazon workflow complete')
            return

        sleep(delay)
        check_feed_done()

        # check upload results

        check_products(check_type='check_after', asins=asins)
        logger.info('Amazon workflow complete')

    except WorkflowError as e:
        logger.critical('Workflow failed with error: {0}'.format(e))

        if len(asins):
            if e.code != 300:
                check_feed_done()

            check_products(check_type='check_after', asins=asins)


@shared_task(name='Delete old unsuitable pairs')
def delete_pairs_unsuitable():
    """ Delete old pairs with unsuitable status from db and then from Amazon inventory """

    messages = []

    for pair in Pair.objects.filter(created__lte=datetime.now(get_current_timezone()) - timedelta(
           days=constants.pair_unsuitable_days_live)).filter(checked__gte=2):
        if len(pair.seller_sku):
            messages.append((pair.seller_sku,))

        if not Order.objects.filter(items=pair).exists():
            pair.delete()

    logger.info('Old pairs with unsuitable status deleted from db')

    if len(messages):
        xml_delete_product_helper.make_body(messages)
    else:
        logger.warning('No messages to delete products in Amazon.')
        return

    # delete filtered products from Amazon

    try:
        response = amazon_feeds_api.api.submit_feed(feed=xml_delete_product_helper.tree,
                                                    feed_type=amazon_feeds_api.feed_types['delete_product'],
                                                    marketplaceids=[amazon_feeds_api.region])

    except amazon_feeds_api.connection_error as e:
        xml_delete_product_helper.reload_tree()
        logger.critical('Unhandled Amazon Feeds api error: {0}.'.format(e))
        return

    xml_delete_product_helper.reload_tree()

    if response.parsed['FeedSubmissionInfo']['FeedProcessingStatus']['value'] != '_SUBMITTED_':
        logger.critical('Feeds Api did not accept messages to delete products. Status: {0}. Messages: {1}.'
                        .format(response.parsed['FeedSubmissionInfo']['FeedProcessingStatus']['value'], messages))
        return

    logger.info('Old pairs deleted from Amazon')


@shared_task(name='Check new orders')
def check_orders():
    """ Get last day orders and create Order objects in db """

    date = datetime.now() - timedelta(days=1) + timedelta(hours=8)
    date = datetime.strftime(date, '%Y-%m-%dT%H:%M:%S')

    try:
        response = amazon_orders_api.api.list_orders(created_after=date, marketplaceids=[amazon_orders_api.region])

    except amazon_orders_api.connection_error as e:
        logger.critical('Amazon Orders api unhandled error: {0}.'.format(e))
        return

    if not len(response.parsed['Orders']):
        logger.warning('There are no orders in response.')
        return

    try:
        response.parsed['Orders']['Order'][0]

    except KeyError:
        process_order(response.parsed['Orders']['Order'])

    else:
        for order in response.parsed['Orders']['Order']:
            process_order(order)

    logger.info('Check for new orders complete.')


def process_order(order):
    """ Process Amazon order from ListOrders response """

    if order['OrderStatus']['value'] != 'Unshipped':
        return

    new_order = Order()
    new_order.order_id = order['AmazonOrderId']['value']

    # check if order already exists

    if Order.objects.filter(order_id=new_order.order_id).exists():
        return

    # parse order shipping info

    new_order.shipping_info = {'BuyerName': order['BuyerName']['value']}

    try:
        order['ShippingAddress']

    except KeyError:
        pass

    else:
        for field in shipping_info_fields:
            try:
                new_order.shipping_info[field] = order['ShippingAddress'][field]['value']

            except KeyError:
                continue

    # parse order items

    items = []

    try:
        response_order = amazon_orders_api.api.list_order_items(new_order.order_id)

    except amazon_orders_api.connection_error as e:
        logger.warning('Amazon Orders api unhandled error: {0}.'.format(e))
        return

    try:
        response_order.parsed['OrderItems']['OrderItem'][0]

    except KeyError:
        # in one item case

        try:
            item = Pair.objects.get(asin=response_order.parsed['OrderItems']['OrderItem']['ASIN']['value'])

        except ObjectDoesNotExist:
            return

        quantity = int(response_order.parsed['OrderItems']['OrderItem']['QuantityOrdered']['value'])
        new_order.items_counts = {item.id: quantity}

        new_order.amazon_price = float(response_order.parsed['OrderItems']['OrderItem']['ItemPrice']['Amount']
                                       ['value'])
        items.append(item)

    else:
        # in multiple items case

        amazon_price = 0
        items_counts = {}

        for item in response_order.parsed['OrderItems']['OrderItem']:
            try:
                item = Pair.objects.get(asin=item['ASIN']['value'])

            except ObjectDoesNotExist:
                pass

            else:
                items_counts[item.id] = int(item['QuantityOrdered']['value'])

                amazon_price += float(item['ItemPrice']['Amount']['value'])
                items.append(item)

        new_order.items_counts = items_counts
        new_order.amazon_price = amazon_price

    if not len(items):
        return

    date = order['PurchaseDate']['value']
    date = datetime.strptime(date[:date.find('.')], '%Y-%m-%dT%H:%M:%S') - timedelta(hours=8)
    new_order.purchase_date = date.date()
    new_order.save()
    new_order.items.add(*items)
    new_order.set_multi()


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


class WorkflowError(Exception):
    """
    Amazon workflow exception

    codes:
        100 - default code for empty message
        200 - processing is out of time
        300 - feed submit failed
    """

    def __init__(self, message=None, code=100):
        self.message = message
        self.code = code

    def __str__(self):
        if self.message is None:
            return 'WorkflowError empty message. Code: {0}'.format(self.code)

        return '{0}. Code: {1}'.format(self.message, self.code)
