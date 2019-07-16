from re import fullmatch
from time import sleep
from config import constants
from utils import amazon_products_api
from .parsers import get_buybox_price_from_response, get_no_buybox_price_from_response
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

    for part in asins:
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
