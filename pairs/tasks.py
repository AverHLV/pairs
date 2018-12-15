from django.utils.timezone import get_current_timezone
from django.core.exceptions import ObjectDoesNotExist
from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import datetime, timedelta
from config.constants import pair_days_live
from utils import amazon_orders_api, amazon_feeds_api, xml_helper
from .models import Pair, Order, shipping_info_fields

logger = get_task_logger(__name__)


@shared_task(name='Update pairs quantity')
def update_pairs_quantity():
    """
    Update the number of pairs in the database using eBay api,
    then update the number in the Amazon inventory
    """

    messages = []

    # update quantities in db from eBay

    for pair in Pair.objects.all():
        pair.check_quantity()

        if len(pair.seller_sku) and pair.quantity is not None:
            messages.append((pair.seller_sku, pair.quantity))

    if len(messages):
        xml_helper.make_body(messages)
    else:
        logger.warning('No messages to update quantity in Amazon.')
        return

    # update quantities in Amazon inventory

    try:
        response = amazon_feeds_api.api.submit_feeds(feed=xml_helper.tree, feed_type=amazon_feeds_api.feed_type,
                                                     marketplaceids=[amazon_feeds_api.region])

    except amazon_feeds_api.connection_error as e:
        logger.critical('Unhandled Amazon Feeds api error: {0}.'.format(e.response))
        xml_helper.reload_tree()
        return

    if response.parsed['FeedProcessingStatus']['value'] != '_SUBMITTED_':
        logger.critical('Feeds Api did not accept messages to update the items quantity. Status: {0}. Messages: {1}.'
                        .format(response.parsed['FeedProcessingStatus']['value'], messages))

    xml_helper.reload_tree()
    logger.info('Pairs quantity update is complete.')


@shared_task(name='Check new orders')
def check_orders():
    """ Get last day orders and create Order objects in db """

    date = datetime.now() - timedelta(days=1) + timedelta(hours=8)
    date = datetime.strftime(date, '%Y-%m-%dT%H:%M:%S')

    try:
        response = amazon_orders_api.api.list_orders(created_after=date, marketplaceids=[amazon_orders_api.region])

    except amazon_orders_api.connection_error as e:
        logger.critical('Amazon Orders api unhandled error: {0}.'.format(e.response))
        return

    if not len(response.parsed['Orders']):
        logger.critical('There are no orders in response.')
        return

    for order in response.parsed['Orders']['Order']:
        if order['OrderStatus']['value'] == 'Unshipped':
            new_order = Order()
            new_order.order_id = order['AmazonOrderId']['value']

            # parse order shipping info

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

            # check if order already exists

            if Order.objects.filter(order_id=new_order.order_id).exists():
                continue

            # parse order items

            items = []

            try:
                response_order = amazon_orders_api.api.list_order_items(new_order.order_id)

            except amazon_orders_api.connection_error as e:
                logger.warning('Amazon Orders api unhandled error: {0}.'.format(e.response))
                continue

            try:
                response_order.parsed['OrderItems']['OrderItem'][0]

            except KeyError:
                # in one item case

                try:
                    item = Pair.objects.get(asin=response_order.parsed['OrderItems']['OrderItem']['ASIN']['value'])

                except ObjectDoesNotExist:
                    continue

                new_order.amazon_price = float(response_order.parsed['OrderItems']['OrderItem']['ItemPrice']['Amount']
                                               ['value'])
                items.append(item)

            else:
                # in multiple items case

                amazon_price = 0

                for item in response_order.parsed['OrderItems']['OrderItem']:
                    try:
                        item = Pair.objects.get(asin=item['ASIN']['value'])

                    except ObjectDoesNotExist:
                        pass

                    else:
                        amazon_price += float(item['ItemPrice']['Amount']['value'])
                        items.append(item)

                new_order.amazon_price = amazon_price

            if not len(items):
                continue

            date = order['PurchaseDate']['value']
            date = datetime.strptime(date[:date.find('.')], '%Y-%m-%dT%H:%M:%S') - timedelta(hours=8)
            new_order.purchase_date = date.date()
            new_order.save()
            new_order.items.add(*items)
            new_order.set_multi()

    logger.info('Check for new orders completed.')


@shared_task(name='Delete old pairs')
def delete_pairs():
    """ Delete old pairs that do not appear in any order """

    for pair in Pair.objects.filter(created__lte=datetime.now(get_current_timezone()) - timedelta(days=pair_days_live)):
        if not Order.objects.filter(items=pair).exists():
            pair.owner.pairs_count -= 1
            pair.owner.save(update_fields=['pairs_count'])
            pair.delete()

    logger.info('Old pairs deleted.')
