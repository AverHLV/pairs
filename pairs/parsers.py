from django.utils.timezone import get_current_timezone
from urllib.request import urlopen
from urllib.error import URLError
from lxml.etree import fromstring, HTMLParser
from re import search
from datetime import datetime
from config.constants import ebay_delivery_months
from utils import logger


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


def get_amazon_upc(asin):
    """ Get item UPC from Amazon item page """

    location = '//li[child::b[contains(text(), "UPC:")]]/text()'

    try:
        response = urlopen('https://www.amazon.com/dp/{0}/'.format(asin)).read().decode('utf8')

    except URLError as e:
        logger.warning('URLError while getting upc: {0}'.format(e))
        return

    tree = fromstring(response, HTMLParser())
    upc = tree.xpath(location)

    if not len(upc):
        return

    return [upc_id for upc_id in upc[0].split(' ') if len(upc_id)]


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


def get_delivery_time(ebay_id):
    """
    Get delivery time in days from eBay item page

    Warning! Server region must be the same as eBay trading region
    """

    possible_locations = [
        '//strong[@class="vi-acc-del-range"]/b/text()',
        '//span[@class="vi-acc-del-range"]/b/text()',
        '//strong[@class="vi-acc-del-range"]/text()',
        '//span[@class="vi-acc-del-range"]/text()'
    ]

    try:
        response = urlopen('https://www.ebay.com/itm/{0}'.format(ebay_id)).read().decode('utf8')

    except URLError as e:
        logger.warning('URLError while getting delivery date: {0}'.format(e))
        return

    # find and parse date string in html response

    tree = fromstring(response, HTMLParser())

    for location in possible_locations:
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

    delivery_date = datetime.now(get_current_timezone()).date()
    delivery_date = delivery_date.replace(day=int(date[5:]), month=ebay_delivery_months[date[:3]])
    current_date = datetime.now(get_current_timezone()).date()

    if current_date > delivery_date and current_date.month == 12 and delivery_date.month in (1, 2, 3):
        delivery_date = delivery_date.replace(year=delivery_date.year + 1)

    return (delivery_date - current_date).days
