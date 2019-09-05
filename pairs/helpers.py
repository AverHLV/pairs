from re import fullmatch
from time import sleep
from config import constants
from utils import amazon_products_api
from .parsers import get_buybox_price_from_response, get_no_buybox_price_from_response, get_my_price_from_response
from .models import Pair, CustomUser


def pairs_search(search_term, user):
    """ Custom search for Pair model """

    if fullmatch('[A-Z0-9]{10}', search_term) is not None:
        # search by owner username

        queryset = Pair.objects.filter(asin=search_term)

    elif fullmatch('[A-Z0-9]{2}-[A-Z0-9]{4}-[A-Z0-9]{4}', search_term) is not None:
        # search by sku

        queryset = Pair.objects.filter(seller_sku=search_term)

    elif fullmatch('[0-9]{12}', search_term) is not None:
        # search by eBay id

        queryset = Pair.objects.filter(ebay_ids__contains=search_term)

    else:
        # search by owner username

        try:
            owner = CustomUser.objects.get(username=search_term)

        except CustomUser.DoesNotExist:
            return Pair.objects.none()

        queryset = Pair.objects.filter(owner=owner)

    if not user.is_moderator:
        return queryset.filter(owner=user)

    return queryset


def get_item_price_info(asins, logger, delay=0.5):
    """
    Create items price info list in format:
        list element: [asin, lowest price, is_buybox_winner]
    """

    result_price_info = []

    asins = [asins[x:x + constants.amazon_get_my_price_items_limit] for x in range(
        0, len(asins), constants.amazon_get_my_price_items_limit
    )]

    logger.info('Getting price info started')

    for part in asins:
        logger.info('Asins part: {}'.format(part))

        # get buybox-existence info

        price_info = [[asin] for asin in part]

        try:
            response = amazon_products_api.api.get_competitive_pricing_for_asin(amazon_products_api.region, part)

        except amazon_products_api.connection_error:
            logger.critical('Getting BB prices failed for part: {0}'.format(part))
            return

        # save info from response to price_info list

        get_buybox_price_from_response(price_info, response)

        # get price info for no-buybox items

        asins_no_buybox = [asin_info[0] for asin_info in price_info if asin_info[2] is None]

        if not len(asins_no_buybox):
            result_price_info += price_info
            continue

        try:
            response = amazon_products_api.api.get_lowest_offer_listings_for_asin(
                amazon_products_api.region, asins_no_buybox, condition='New'
            )

        except amazon_products_api.connection_error:
            result_price_info += price_info
            logger.critical('Getting listing prices failed for part: {0}'.format(part))
            return

        # save info from response to asins_no_buybox list

        get_no_buybox_price_from_response(asins_no_buybox, response)

        # set new prices in price_info list

        for asin_info in asins_no_buybox:
            for price_info_elem in price_info:
                if asin_info[0] == price_info_elem[0]:
                    price_info_elem[1] = asin_info[1]
                    break

        result_price_info += price_info
        sleep(delay)

    return result_price_info


def update_my_prices():
    """ Update items current prices in db """

    for pair in Pair.objects.all().exclude(seller_sku=''):
        try:
            response = amazon_products_api.api.get_my_price_for_sku(amazon_products_api.region, [pair.seller_sku])

        except amazon_products_api.connection_error as e:
            print('Unhandled error: {}'.format(e))
            continue

        pair.amazon_current_price = get_my_price_from_response(response)[0]
        pair.save(update_fields=['amazon_current_price'])


def check_profit(amazon_price: float, ebay_prices: list) -> tuple:
    """
    Check minimum profit for asin and all eBay ids and calculate approximate price for Amazon

    :param amazon_price: Amazon item lowest price
    :param ebay_prices: list of eBay items prices
    :return: tuple: check result and calculated prices in format:
        (Check result - True or False, Amazon minimum price, Amazon approximate price)
    """

    prices, chosen_ebay_prices = [], []

    for ebay_price in ebay_prices:
        if not ebay_price:
            continue

        price = 0

        for interval in constants.profit_intervals:
            if interval[0] <= ebay_price < interval[1]:
                price = ebay_price * constants.profit_intervals[interval] / constants.profit_percentage
                prices.append(price)
                chosen_ebay_prices.append(ebay_price)
                break

        if amazon_price:
            if price + constants.profit_buffer >= amazon_price:
                return False, None, None

    # getting approximate price

    if not len(prices):
        return False, None, None

    max_ebay_price_coeff = 0
    max_price = max(prices)
    max_ebay_price = chosen_ebay_prices[prices.index(max_price)]

    for interval in constants.amazon_approximate_price_percent:
        if interval[0] <= max_ebay_price < interval[1]:
            max_ebay_price_coeff = constants.amazon_approximate_price_percent[interval]

    amazon_minimum_price = round(min(prices), 2)
    amazon_approximate_price = round(max_price + max_ebay_price * max_ebay_price_coeff, 2)
    return True, amazon_minimum_price, amazon_approximate_price
