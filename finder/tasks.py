from celery import shared_task
from celery.utils.log import get_task_logger

from config import constants
from utils import ebay_trading_api, secret_dict
from decorators import log_work_time
from pairs.helpers import check_profit

from pairs.parsers import (
    get_delivery_time, get_seller_id_from_response, get_ebay_price_from_response, get_ebay_quantity_from_response
)

from .interface import AmazonFinder, KeepaFinder

logger = get_task_logger(__name__)
am_finder = AmazonFinder()
keepa_finder = KeepaFinder(secret_dict['keepa_key'])


@shared_task(name='Run finder')
@log_work_time('Run finder task')
def run_finder(uri: str, use_proxy: bool, save: bool = False, username: str = 'aver') -> None:
    """ Find pairs in Amazon and eBay """

    from pairs.models import Pair, NotAllowedSeller
    from users.models import CustomUser

    info_results = am_finder(uri, use_proxy)

    if not len(info_results):
        logger.critical('Empty Amazon products info results')
        return

    pairs = {}
    products_all_number = len(info_results.keys())
    blacklist = [na_seller.ebay_user_id for na_seller in NotAllowedSeller.objects.all()]

    # find pairs info on eBay and validate items data

    for asin in info_results:
        # avoid already existing asins from result

        if Pair.objects.filter(asin=asin).exists():
            continue

        quantity = 0
        ebay_ids = []
        ebay_price = []

        for ebay_id in info_results[asin]['ebay_ids']:
            try:
                response = ebay_trading_api.api.execute('GetItem', {'ItemID': ebay_id})

            except ebay_trading_api.connection_error as e:
                logger.warning('eBay api unhandled error: {}'.format(e))
                continue

            # checking seller statistics

            if int(response.reply.Item.Seller.FeedbackScore) <= constants.ebay_min_feedback_score:
                continue

            if float(response.reply.Item.Seller.PositiveFeedbackPercent) <= constants.ebay_min_positive_percentage:
                continue

            # check for item seller status

            if get_seller_id_from_response(response) in blacklist:
                continue

            # item delivery time

            delivery_time = get_delivery_time(ebay_id)

            if delivery_time is None or delivery_time > constants.ebay_max_delivery_time:
                continue

            # getting eBay price

            ebay_price.append(get_ebay_price_from_response(response))
            ebay_ids.append(ebay_id)
            quantity += get_ebay_quantity_from_response(response)

            if len(ebay_ids) == constants.ebay_ids_max_count:
                break

        ebay_price_set = set(ebay_price)

        if len(ebay_price_set) == 1 and not list(ebay_price_set)[0]:
            continue

        # check profits

        profit_check, amazon_minimum_price, amazon_approximate_price = \
            check_profit(info_results[asin]['price'], ebay_price)

        if not profit_check:
            continue

        # create new pair

        pairs[asin] = Pair(asin=asin,
                           ebay_ids=';'.join(ebay_ids),
                           amazon_minimum_price=amazon_minimum_price,
                           amazon_approximate_price=amazon_approximate_price,
                           quantity=quantity,
                           owner=CustomUser.objects.get(username=username))

    # validate items Amazon data by Keepa and save found pairs

    pairs_number = 0

    for asin in keepa_finder(list(pairs.keys())):
        pairs_number += 1

        if save:
            pairs[asin].save()

    print('All:', products_all_number, 'pairs number:', pairs_number)
