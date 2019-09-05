from celery import shared_task
from celery.utils.log import get_task_logger

from config import constants
from utils import ebay_finding_api, secret_dict
from pairs.helpers import check_profit
from pairs.parsers import get_delivery_time
from .interface import AmazonFinder, KeepaFinder

logger = get_task_logger(__name__)
am_finder = AmazonFinder()
keepa_finder = KeepaFinder(secret_dict['keepa_key'])


@shared_task(name='Run finder')
def run_finder(uri: str, save: bool = False, username: str = 'aver') -> None:
    """ Find pairs in Amazon and eBay """

    from pairs.models import Pair, NotAllowedSeller
    from users.models import CustomUser

    info_results = am_finder(uri)

    if not len(info_results):
        logger.critical('Empty Amazon products info results')
        return

    pairs = {}
    products_all_number = len(info_results.keys())

    # find pairs on eBay and validate items data

    for asin in info_results:
        # avoid already existing asins from result

        if Pair.objects.filter(asin=asin).exists():
            continue

        # search by Finding API

        try:
            response = ebay_finding_api.api.execute(
                'findItemsByKeywords', {'keywords': info_results[asin]['title'], 'outputSelector': 'SellerInfo'}
            )

        except ebay_finding_api.connection_error as e:
            logger.warning('eBay api unhandled error: {}'.format(e))
            continue

        if not int(response.reply.searchResult.get('_count')):
            continue

        ebay_ids = []
        ebay_price = []
        blacklist = [na_seller.ebay_user_id for na_seller in NotAllowedSeller.objects.all()]

        # validate api response

        for item in response.reply.searchResult.item:
            if len(ebay_ids) == constants.ebay_ids_max_count:
                break

            ebay_id = item.itemId

            # listing status checking

            if item.sellingStatus.sellingState != 'Active' or item.returnsAccepted != 'true':
                continue

            # checking seller statistics

            if int(item.sellerInfo.feedbackScore) <= constants.ebay_min_feedback_score:
                continue

            positive_feedback = float(item.sellerInfo.positiveFeedbackPercent)

            if positive_feedback <= constants.ebay_min_positive_percentage:
                continue

            # item delivery time

            delivery_time = get_delivery_time(ebay_id)

            if delivery_time is None or delivery_time > constants.ebay_max_delivery_time:
                continue

            # check for item seller status

            if item.sellerInfo.sellerUserName in blacklist:
                continue

            # price getting

            price = float(item.sellingStatus.currentPrice.value)

            try:
                shipping_cost = float(item.shippingInfo.shippingServiceCost.value)

            except AttributeError:
                shipping_cost = 0

            ebay_price.append(price + shipping_cost)
            ebay_ids.append(ebay_id)

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
                           owner=CustomUser.objects.get(username=username))

    # validate items Amazon data by Keepa and save found pairs

    for asin in keepa_finder(list(pairs.keys())):
        pairs[asin].check_quantity()

        if save:
            pairs[asin].save()

    print('All:', products_all_number, 'pairs number:', len(pairs))
