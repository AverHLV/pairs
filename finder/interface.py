import logging
import asyncio

from aiohttp import client_exceptions, ClientSession, ClientTimeout
from django.core.exceptions import ImproperlyConfigured
from keepa import Keepa
from numpy import isnan
from lxml import etree

from datetime import datetime, timedelta
from re import sub

from config import constants
from pairs.helpers import get_item_price_info
from decorators import log_work_time

logger = logging.getLogger('finder')


class AmazonFinder(object):
    """ Amazon _products information finder """

    _headers = {'Connection': 'close'}
    _parser = etree.HTMLParser()
    _timeout = ClientTimeout(total=constants.timeout)
    _ebay_uri = 'https://www.ebay.com/sch/i.html'
    _ebay_params = {'_nkw': '', '_ipg': 100, 'LH_BIN': 1, 'LH_ItemCondition': 3, 'LH_PrefLoc': 1, 'LH_RPA': 1}
    _proxy_uri = 'http://pubproxy.com/api/proxy?format=txt&type=http&country=US'

    def __init__(self, uri: str = None, use_proxy: bool = True):
        """
        AmazonFinder initialization

        :param uri: Amazon search uri
        :param use_proxy: use proxy for requests to Amazon or not
        """

        if uri is None:
            return

        self._session = None
        self._pages_number = None
        self._proxy = None
        self._pages = []
        self._asins = []
        self._products = {}

        self._use_proxy = use_proxy
        self._amazon_uri = sub(r'&page=\d+', '', uri) + '&page={page_number}'

    @log_work_time('AmazonFinder')
    def __call__(self, *args, **kwargs) -> dict:
        """ Reinitialize for new uri and find products info """

        self.__init__(*args, **kwargs)
        self._run_loop()

        if self._pages_number is None:
            return {}

        self._process_pages()
        self._asins = list(self._products.keys())
        self._run_loop(ebay=True)
        self._process_pages(ebay=True)

        if not len(self._asins):
            logger.critical('No asins for getting prices')
            return {}

        self._get_prices()

        return self._products

    async def _request(self, uri: str, search_term: str = None, params: dict = None, proxy: str = None) -> str:
        """
        Send GET request

        :param uri: request uri
        :param search_term: uri parameters
        :param params: uri parameters
        :param proxy: request proxy
        :return: html str response
        """

        if search_term is not None:
            self._ebay_params['_nkw'] = search_term
            params = self._ebay_params

        try:
            async with self._session.get(uri, params=params, proxy=proxy) as response:
                return await response.text()

        except client_exceptions.ServerTimeoutError:
            logger.critical('Request timeout error, url: {}'.format(uri))

        except client_exceptions.ClientConnectorError:
            logger.critical('Request connection error, url: {}'.format(uri))

        except client_exceptions.ClientOSError:
            logger.critical('Request connection reset, url: {}'.format(uri))

        except client_exceptions.ServerDisconnectedError:
            logger.critical('Server refused the request, url: {}'.format(uri))

    async def _get_first_page(self) -> None:
        """ Get first products page for number of pages """

        response = await self._request(self._amazon_uri.format(page_number=1), proxy=self._proxy)

        if response is None:
            logger.critical('Getting pages number failed while first request')
            return

        self._pages.append(etree.fromstring(response, self._parser))

        try:
            self._pages_number = int(self._pages[0].xpath(r'//ul[@class="a-pagination"]/li[6]/text()')[0])

        except (IndexError, ValueError) as e:
            logger.critical('Getting pages number failed, error: {}'.format(e))

    async def _send_requests(self, ebay: bool) -> None:
        """ Gather products lists pages via GET requests """

        self._pages = []

        # make requests

        if not ebay:
            responses = await asyncio.gather(
                *[self._request(self._amazon_uri.format(page_number=page), proxy=self._proxy)
                  for page in range(self._pages_number + 1)],
                return_exceptions=True
            )

        else:
            responses = await asyncio.gather(
                *[self._request(self._ebay_uri, search_term=self._products[asin]['title']) for asin in self._asins],
                return_exceptions=True
            )

        # parse responses

        values_to_delete = []

        for i in range(len(responses)):
            if isinstance(responses[i], str):
                self._pages.append(etree.fromstring(responses[i], self._parser))

            else:
                if ebay:
                    self._products.pop(self._asins[i])
                    values_to_delete.append(self._asins[i])

                logger.warning('Getting item info error: {}'.format(responses[i]))

        # delete asins

        if ebay:
            for value in values_to_delete:
                self._asins.remove(value)

    def _run_loop(self, ebay: bool = False) -> None:
        """ Run ioloop and wait until all requests will be done """

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._session = ClientSession(headers=self._headers, timeout=self._timeout)

        try:
            if not ebay:
                if self._use_proxy:
                    # get proxy

                    self._proxy = loop.run_until_complete(self._request(self._proxy_uri))

                    if self._proxy is None:
                        logger.warning('AmazonFinder: getting proxy failed')

                    else:
                        self._proxy = 'http://' + self._proxy

                # start sending requests

                loop.run_until_complete(self._get_first_page())

                if self._pages_number is None:
                    return

                elif self._pages_number > 1:
                    loop.run_until_complete(self._send_requests(ebay))

            else:
                loop.run_until_complete(self._send_requests(ebay))

        finally:
            loop.run_until_complete(self._session.close())
            loop.close()

    def _find_products_info(self, tree: etree) -> None:
        """ Find necessary products info in html elements """

        products = tree.xpath('//div[@data-asin]')

        if not len(products):
            logger.warning('Empty products list before finding info')
            return

        for product in products:
            asin = product.get('data-asin')
            title = product.xpath('.//img')[0].get('alt')

            if asin is None or len(asin) != constants.asin_length:
                continue

            if title is None or not len(title):
                continue

            title = sub(r'[^0-9a-z ]', '', title.lower())
            title = sub(r' {2,}', ' ', ' ' + title + ' ')
            title = sub(r' ({0}) '.format('|'.join(constants.stopwords)), ' ', title)
            title = sub(r'^ | $', '', title)
            self._products[asin] = {'title': ' '.join(title.split()[:constants.title_n_words])}

    @staticmethod
    def _find_ebay_products_info(tree: etree) -> (list, None):
        """ Find necessary eBay products info in html elements """

        products = tree.xpath('//li[@class="s-item   "]')

        if not len(products):
            logger.warning('Empty eBay products list before finding info')
            return

        ebay_ids = []

        for product in products[6:]:
            ebay_id = product.xpath('//a[@data-id]')

            if not len(ebay_id):
                continue

            ebay_id = ebay_id[0].get('data-id')

            if ebay_id is None or len(ebay_id) != constants.ebay_id_length:
                continue

            ebay_ids.append(ebay_id)

        if len(ebay_ids):
            return ebay_ids

    def _process_pages(self, ebay: bool = False) -> None:
        """ Process previously found pages """

        if not len(self._pages):
            logger.critical('Pages list is empty')
            return

        if not ebay:
            for page in self._pages:
                self._find_products_info(page)

        else:
            values_to_delete = []

            for i in range(len(self._pages)):
                ebay_ids = self._find_ebay_products_info(self._pages[i])

                if ebay_ids is not None:
                    self._products[self._asins[i]]['ebay_ids'] = ebay_ids

                else:
                    self._products.pop(self._asins[i])
                    values_to_delete.append(self._asins[i])

            for value in values_to_delete:
                self._asins.remove(value)

    def _get_prices(self) -> None:
        """ Receive lowest prices for products """

        for price in get_item_price_info(self._asins, logger):
            self._products[price[0]]['price'] = price[1]


class KeepaFinder(object):
    """ Keepa API client for finding and analyzing product information """

    def __init__(self, secret_key: str):
        """
        KeepaFinder initialization

        :param secret_key: 64 character secret key
        """

        self._products = {}

        try:
            self.api = Keepa(secret_key)

        except Exception:
            # no custom exception in keepa interface for this case

            raise ImproperlyConfigured('Invalid Keepa API secret key')

    @log_work_time('KeepaFinder')
    def __call__(self, products: list) -> list:
        """ Find and analyze Amazon products statistics """

        if not len(products):
            return []

        self._products = {}
        self._products_history(products)

        return [asin for asin in self._products
                if self._products[asin]['amazon']
                and self.analyze_sales(self._products[asin]['sales'])
                and self.analyze_offers(self._products[asin]['offers'])]

    def _products_history(self, asins: list) -> None:
        """
        Get product information for given asins

        :param asins: list of Amazon ASIN strings
        :return: dictionary in format:
            {asin: {sales: list, offers: list, amazon: bool}, }
        """

        try:
            result = self.api.query(asins)

        except Exception as e:
            logger.critical('Keepa request error: {}'.format(e))
            return

        # fill products dictionary

        for product_index in range(len(asins)):
            sales = result[product_index]['data']['SALES']
            offers = result[product_index]['data']['COUNT_NEW']

            if isnan(sales[0]) or isnan(offers[0]):
                logger.warning('No data in keepa for asin: {}'.format(asins[product_index]))
                continue

            # delete values == -1 from sales and offers and time arrays

            sales_necessary_indexes = sales != -1
            offers_necessary_indexes = offers != -1

            sales = sales[sales_necessary_indexes]
            offers = offers[offers_necessary_indexes]

            if not len(sales) or not len(offers):
                logger.warning('Empty arrays after clearing for asin: {}'.format(asins[product_index]))
                continue

            sales_index = self.actualize(result[product_index]['data']['SALES_time'][sales_necessary_indexes])
            offers_index = self.actualize(result[product_index]['data']['COUNT_NEW_time'][offers_necessary_indexes])

            if sales_index == -1 or offers_index == -1:
                logger.warning('No actual data in keepa for asin: {}'.format(asins[product_index]))
                continue

            # choose only actual data from arrays

            self._products[asins[product_index]] = {
                'sales': list(sales[sales_index:]),
                'offers': list(offers[offers_index:]),
                'amazon': isnan(result[product_index]['data']['AMAZON'][0])
            }

    @staticmethod
    def actualize(time_data: list) -> int:
        """
        Find left actual timestamp index

        :param time_data: list of datetime.datetime
        :return: integer, left actual index, special values:
            0 - whole data array fits
            -1 - whole array does not fit
        """

        threshold = datetime.now().date() - timedelta(days=30 * constants.threshold_month_number)

        for index in range(len(time_data) - 1, -1, -1):
            if time_data[index].date() < threshold:
                return index + 1 if index < len(time_data) - 1 else -1

        return 0

    @staticmethod
    def analyze_offers(offers: list) -> bool:
        """ Set the mark for offers, False, if one seller for all time, True - vice versa """

        unique_values = list(set(offers))

        if len(unique_values) == 1 and unique_values[0] == 1:
            return False

        return True

    @staticmethod
    def analyze_sales(sales: list) -> bool:
        """ Set the mark for sales, True if there is a %month number% rank drops, False - vice versa """

        drop_number = 0

        for i in range(len(sales) - 1):
            if 100 - ((sales[i + 1] * 100) / sales[i]) >= constants.rank_drop_percentage:
                drop_number += 1

                if drop_number >= constants.threshold_month_number:
                    return True

        return False
