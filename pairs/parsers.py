import logging

from django.utils.timezone import get_current_timezone
from requests import get, exceptions
from lxml import etree

from re import search
from datetime import datetime

from config import constants

logger = logging.getLogger('custom')
parser = etree.HTMLParser()
current_timezone = get_current_timezone()


def request(uri: str, headers: dict = None) -> str:
    """ Make GET request to given uri """

    try:
        return get(uri, headers=headers, timeout=constants.requests_timeout).text

    except exceptions.Timeout:
        logger.critical('Parsers request: timeout occurred, uri: {}'.format(uri))

    except exceptions.HTTPError as e:
        logger.critical('Parsers request: http error: {0}, uri: {1}'.format(e, uri))

    except exceptions.ConnectionError as e:
        logger.critical('Parsers request: connection error: {0}, uri: {1}'.format(e, uri))


# Amazon MWS response parsers


def get_rank_from_response(response):
    """ Get sales rank from GetMatchingProductForId response """

    try:
        response.parsed['Products']['Product']['SalesRankings']['SalesRank']

    except KeyError:
        return 0

    try:
        response.parsed['Products']['Product']['SalesRankings']['SalesRank'][0]

    except KeyError:
        return int(response.parsed['Products']['Product']['SalesRankings']['SalesRank']['Rank']['value'])

    else:
        return int(response.parsed['Products']['Product']['SalesRankings']['SalesRank'][0]['Rank']['value'])


def get_price_from_response(response):
    """ Get item price from GetLowestPricedOffersForASIN response """

    try:
        response.parsed['Summary']['BuyBoxPrices']

    except KeyError:
        # if no BuyBox

        try:
            response.parsed['Summary']['LowestPrices']['LowestPrice'][0]

        except KeyError:
            try:
                price = response.parsed['Summary']['LowestPrices']['LowestPrice']['LandedPrice']['Amount']['value']
                price = float(price)

            except (KeyError, ValueError):
                try:
                    price = response.parsed['Summary']['LowestPrices']['LowestPrice']['ListingPrice']['Amount']['value']
                    price = float(price)

                except (KeyError, ValueError):
                    return 0

            if response.parsed['Summary']['LowestPrices']['LowestPrice']['condition']['value'] == 'new':
                return price

            return 0

        else:
            try:
                prices = [float(price['LandedPrice']['Amount']['value'])
                          for price in response.parsed['Summary']['LowestPrices']['LowestPrice']
                          if price['condition']['value'] == 'new']

            except (KeyError, ValueError):
                try:
                    prices = [float(price['ListingPrice']['Amount']['value'])
                              for price in response.parsed['Summary']['LowestPrices']['LowestPrice']
                              if price['condition']['value'] == 'new']

                except (KeyError, ValueError):
                    return 0

            if not len(prices):
                return 0

            return min(prices)

    else:
        # if BuyBox exists

        try:
            response.parsed['Summary']['BuyBoxPrices']['BuyBoxPrice'][0]

        except KeyError:
            try:
                price = response.parsed['Summary']['BuyBoxPrices']['BuyBoxPrice']['LandedPrice']['Amount']['value']
                price = float(price)

            except (KeyError, ValueError):
                try:
                    price = response.parsed['Summary']['BuyBoxPrices']['BuyBoxPrice']['ListingPrice']['Amount']['value']
                    price = float(price)

                except (KeyError, ValueError):
                    return 0

            if response.parsed['Summary']['BuyBoxPrices']['BuyBoxPrice']['condition']['value'] == 'New':
                return price

            return 0

        else:
            try:
                prices = [float(price['LandedPrice']['Amount']['value'])
                          for price in response.parsed['Summary']['BuyBoxPrices']['BuyBoxPrice']
                          if price['condition']['value'] == 'New']

            except (KeyError, ValueError):
                try:
                    prices = [float(price['ListingPrice']['Amount']['value'])
                              for price in response.parsed['Summary']['BuyBoxPrices']['BuyBoxPrice']
                              if price['condition']['value'] == 'New']

                except (KeyError, ValueError):
                    return 0

            if not len(prices):
                return 0

            return min(prices)


def get_my_price_from_response(response):
    """ Get item price from GetMyPriceForASIN response """

    try:
        response.parsed[0]

    except KeyError:
        # if not iterable

        try:
            raw_price = response.parsed['Product']['Offers']['Offer']['BuyingPrice']['LandedPrice']['Amount']['value']
            price = float(raw_price)

        except (KeyError, ValueError):
            try:
                raw_price = response.parsed['Product']['Offers']['Offer']['BuyingPrice']['ListingPrice']['Amount'][
                    'value']
                price = float(raw_price)

            except (KeyError, ValueError):
                return [0]

        return [price]

    else:
        # if iterable

        try:
            return [float(product['Product']['Offers']['Offer']['BuyingPrice']['LandedPrice']['Amount']['value'])
                    for product in response.parsed]

        except (KeyError, ValueError):
            try:
                return [float(product['Product']['Offers']['Offer']['BuyingPrice']['ListingPrice']['Amount']['value'])
                        for product in response.parsed]

            except (KeyError, ValueError):
                return [0]


def get_buybox_price_from_response(price_info, response):
    """
    Append given price_info list with asins by GetCompetitivePricingForASIN response in format:
        price_info element: [asin, price, is_buybox_winner]
    """

    def fill_price_info(index):
        try:
            comp_price_dict[0]

        except KeyError:
            try:
                price = float(comp_price_dict['Price']['LandedPrice']['Amount']['value'])

            except (KeyError, ValueError):
                try:
                    price = float(comp_price_dict['Price']['ListingPrice']['Amount']['value'])

                except (KeyError, ValueError):
                    price = 0

            price_info[index].append(price)

            if comp_price_dict['belongsToRequester']['value'] == 'true':
                price_info[index].append(True)
            else:
                price_info[index].append(False)

        else:
            actual_comp_price = None

            for comp_price in comp_price_dict:
                if comp_price['CompetitivePriceId']['value'] == '1':
                    actual_comp_price = comp_price

            if actual_comp_price is None:
                actual_comp_price = comp_price_dict[0]

            try:
                price = float(actual_comp_price['Price']['LandedPrice']['Amount']['value'])

            except (KeyError, ValueError):
                try:
                    price = float(actual_comp_price['Price']['ListingPrice']['Amount']['value'])

                except (KeyError, ValueError):
                    price = 0

            price_info[index].append(price)

            if actual_comp_price['belongsToRequester']['value'] == 'true':
                price_info[index].append(True)
            else:
                price_info[index].append(False)

    # parse response

    try:
        response.parsed[0]

    except KeyError:
        if not len(response.parsed['Product']['CompetitivePricing']['CompetitivePrices']):
            price_info[0].append(0)
            price_info[0].append(None)

        else:
            comp_price_dict = response.parsed['Product']['CompetitivePricing']['CompetitivePrices']['CompetitivePrice']
            fill_price_info(0)

    else:
        for i in range(len(response.parsed)):
            try:
                response.parsed[i]['Product']

            except KeyError:
                price_info[i].append(0)
                price_info[i].append(None)

            else:
                if not len(response.parsed[i]['Product']['CompetitivePricing']['CompetitivePrices']):
                    price_info[i].append(0)
                    price_info[i].append(None)

                else:
                    comp_price_dict = response.parsed[i]['Product']['CompetitivePricing']['CompetitivePrices'][
                        'CompetitivePrice']
                    fill_price_info(i)


def get_no_buybox_price_from_response(asins_no_buybox, response):
    """
    Append given asins_no_buybox list with lowest listing prices from GetLowestOfferListingsForASIN response
    in format:
        asins_no_buybox element: (asin, price)
    """

    try:
        response.parsed[0]

    except KeyError:
        # if response for one item

        if not len(response.parsed['Product']['LowestOfferListings']):
            # if not available

            asins_no_buybox[0] = asins_no_buybox[0], 0
            return

        try:
            response.parsed['Product']['LowestOfferListings']['LowestOfferListing'][0]

        except KeyError:
            listing_info = response.parsed['Product']['LowestOfferListings']['LowestOfferListing']

            try:
                price = float(listing_info['Price']['LandedPrice']['Amount']['value'])

            except (KeyError, ValueError):
                try:
                    price = float(listing_info['Price']['ListingPrice']['Amount']['value'])

                except (KeyError, ValueError):
                    price = 0

            asins_no_buybox[0] = asins_no_buybox[0], price

        else:
            try:
                prices = [float(price['Price']['LandedPrice']['Amount']['value'])
                          for price in response.parsed['Product']['LowestOfferListings']['LowestOfferListing']]

            except (KeyError, ValueError):
                try:
                    prices = [float(price['Price']['ListingPrice']['Amount']['value'])
                              for price in response.parsed['Product']['LowestOfferListings']['LowestOfferListing']]

                except (KeyError, ValueError):
                    prices = [0]

            asins_no_buybox[0] = asins_no_buybox[0], min(prices)

    else:
        # if multiple items

        for i in range(len(response.parsed)):
            if not len(response.parsed[i]['Product']['LowestOfferListings']):
                # if not available

                asins_no_buybox[i] = asins_no_buybox[i], 0
                continue

            try:
                response.parsed[i]['Product']['LowestOfferListings']['LowestOfferListing'][0]

            except KeyError:
                listing_info = response.parsed[i]['Product']['LowestOfferListings']['LowestOfferListing']

                try:
                    price = float(listing_info['Price']['LandedPrice']['Amount']['value'])

                except (KeyError, ValueError):
                    try:
                        price = float(listing_info['Price']['ListingPrice']['Amount']['value'])

                    except (KeyError, ValueError):
                        price = 0

                asins_no_buybox[i] = asins_no_buybox[i], price

            else:
                try:
                    prices = [float(price['Price']['LandedPrice']['Amount']['value'])
                              for price in response.parsed[i]['Product']['LowestOfferListings']['LowestOfferListing']]

                except (KeyError, ValueError):
                    try:
                        prices = [float(price['Price']['ListingPrice']['Amount']['value'])
                                  for price in response.parsed[i]['Product']['LowestOfferListings'][
                                      'LowestOfferListing']]

                    except (KeyError, ValueError):
                        prices = [0]

                asins_no_buybox[i] = asins_no_buybox[i], min(prices)


# Custom response parsers


def get_amazon_upc(asin: str) -> (list, None):
    """ Get item UPC from Amazon item page """

    response = request('https://www.amazon.com/dp/{}'.format(asin), headers={'Connection': 'close'})

    if response is None:
        return

    tree = etree.fromstring(response, parser)
    upc = tree.xpath('//li[child::b[contains(text(), "UPC:")]]/text()')

    if not len(upc):
        return

    return [upc_id for upc_id in upc[0].split(' ') if len(upc_id)]


def get_delivery_time(ebay_id: str) -> (int, None):
    """
    Get delivery time in days from eBay item page

    Warning! Server region must be the same as eBay trading region
    """

    response = request('https://www.ebay.com/itm/{}'.format(ebay_id), headers={'Connection': 'close'})

    if response is None:
        return

    # find and parse date string in html response

    tree = etree.fromstring(response, parser)

    for location in ('//strong[@class="vi-acc-del-range"]/b/text()',
                     '//strong[@class="vi-acc-del-range"]/text()',
                     '//span[@class="vi-acc-del-range"]/b/text()',
                     '//span[@class="vi-acc-del-range"]/text()'):
        date = tree.xpath(location)

        if len(date):
            break

    else:
        return

    date = search(r'[A-Z][a-z]{2}\. \d{1,2}', date[0])

    if date is None:
        return

    date = date.group()

    if not len(date):
        return

    # calculate number of delivery days

    delivery_date = datetime.now(current_timezone).date()
    delivery_date = delivery_date.replace(day=int(date[5:]), month=constants.ebay_delivery_months[date[:3]])
    current_date = datetime.now(current_timezone).date()

    if current_date > delivery_date:
        return

    return (delivery_date - current_date).days


# eBay APIs response parsers


def get_ebay_price_from_response(response):
    """ Get eBay item price and shipping cost from GetItem response """

    try:
        price = float(response.reply.Item.BuyItNowPrice.value)

        if not price:
            price = float(response.reply.Item.StartPrice.value)

    except AttributeError:
        return 0

    lowest_shipping_cost = 0

    try:
        response.reply.Item.ShippingDetails.ShippingServiceOptions[0]

    except TypeError:
        try:
            shipping_cost = response.reply.Item.ShippingDetails.ShippingServiceOptions
            lowest_shipping_cost = float(shipping_cost.ShippingServiceCost.value)

        except AttributeError:
            return price

    else:
        try:
            for shipping_cost_info in response.reply.Item.ShippingDetails.ShippingServiceOptions:
                shipping_cost = float(shipping_cost_info.ShippingServiceCost.value)

                if shipping_cost < lowest_shipping_cost:
                    lowest_shipping_cost = shipping_cost

        except AttributeError:
            return price

    return price + lowest_shipping_cost


def get_ebay_quantity_from_response(response):
    """ Get eBay item quantity from GetItem response """

    if response.reply.Item.SellingStatus.ListingStatus == 'Active':
        return int(response.reply.Item.Quantity) - int(response.reply.Item.SellingStatus.QuantitySold)

    return 0


def get_seller_id_from_response(response):
    """ Get eBay seller UserID from GetItem response """

    seller_id = response.reply.Item.Seller.UserID

    if not len(seller_id):
        return

    return seller_id
