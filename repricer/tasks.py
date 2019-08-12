from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils.timezone import get_current_timezone

from datetime import datetime, timedelta

from config import constants
from pairs.parsers import get_my_price_from_response
from pairs.tasks import set_prices, set_prices_local
from pairs.helpers import get_item_price_info
from utils import amazon_products_api
from .models import RepricerStats

logger = get_task_logger(__name__)


def calc_current_prices():
    """ Set items inventory prices from Amazon """

    prices = []
    from pairs.models import Pair
    asins = [pair.asin for pair in Pair.objects.exclude(seller_sku='')]

    for asin in asins:
        response = amazon_products_api.api.get_my_price_for_asin(amazon_products_api.region, [asin])
        prices.append((asin, get_my_price_from_response(response)[0]))

    set_prices_local(prices, for_current_price=True)


@shared_task(name='Repricer')
def reprice(strategy=1):
    """ Create reprice configuration for in-inventory items and submit it """

    from pairs.models import Pair
    asins = [pair.asin for pair in Pair.objects.filter(amazon_current_price__gt=0).exclude(seller_sku='')]

    if not len(asins):
        logger.warning('No items for repricing')
        return

    prices = []
    prices_info = get_item_price_info(asins, logger)

    if prices_info is None:
        return

    for asin_info in prices_info:
        pair = Pair.objects.get(asin=asin_info[0])
        price = asin_info[1]
        buybox_status = asin_info[2]

        # change price if too low

        minimum_price_granted = False

        if not price:
            price = pair.amazon_approximate_price

        elif price < pair.amazon_minimum_price:
            price = pair.amazon_minimum_price
            minimum_price_granted = True

        # actions according to the BuyBox status

        if buybox_status is None:
            # if no BuyBox

            if price != pair.amazon_current_price:
                if strategy == 1 and not minimum_price_granted:
                    price -= 0.01

                prices.append((pair.asin, price))

            else:
                pair.set_buybox_status(False)
                continue

        elif buybox_status:
            # if BuyBox winner

            pair.set_buybox_status(buybox_status)
            continue

        else:
            # if no BuyBox winner

            if pair.is_buybox_winner and price < pair.amazon_current_price:
                if strategy == 1 and not minimum_price_granted:
                    price -= 0.01

                prices.append((pair.asin, price))

            elif strategy == 1 and pair.is_buybox_winner and price == pair.amazon_current_price:
                price -= 0.01
                prices.append((pair.asin, price))

            elif pair.is_buybox_winner and price >= pair.amazon_current_price:
                pair.set_buybox_status(buybox_status)
                continue

            else:
                # if no BuyBox winner earlier

                if price != pair.amazon_current_price:
                    if strategy == 1 and not minimum_price_granted:
                        price -= 0.01

                    prices.append((pair.asin, price))

                else:
                    pair.set_buybox_status(buybox_status)
                    continue

        if buybox_status is None:
            pair.set_buybox_status(False)
        else:
            pair.set_buybox_status(buybox_status)

        pair.amazon_current_price = price
        pair.save(update_fields=['amazon_current_price'])

    RepricerStats().save_stats()
    logger.info('Repricer stats saved')

    if not len(prices):
        logger.info('Empty reprice configuration')
        return

    set_prices(prices)
    logger.info('Reprice configuration set')


@shared_task(name='Delete old repricer info')
def delete_old_repricer_info():
    """ Delete old repricer statistics info """

    for stats in RepricerStats.objects.filter(created__lte=datetime.now(get_current_timezone()) - timedelta(
           days=constants.old_stats_days_live)):
        stats.delete()

    logger.info('Old reprice info deleted')
