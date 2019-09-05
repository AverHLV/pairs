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

    def __init__(self, uri: str = None):
        """
        AmazonFinder initialization

        :param uri: Amazon search uri
        """

        if uri is None:
            return

        self._session = None
        self._pages_number = None
        self._pages = []
        self._products = {}
        self._uri = uri + '&page={page_number}'

    @log_work_time('AmazonFinder')
    def __call__(self, uri: str) -> dict:
        """ Reinitialize for new uri and find _products info """

        self.__init__(uri)
        self._run_loop()
        self._process_pages()
        self._get_prices()
        return self._products

    async def _request(self, page_number: int = 1):
        """
        Send GET request

        :param page_number: positive integer
        :return: html str response
        """

        try:
            async with self._session.get(self._uri.format(page_number=page_number)) as response:
                return await response.text()

        except client_exceptions.ServerTimeoutError:
            logger.critical('Request timeout error, page: {0}, url: {1}'.format(page_number, self._uri))

        except client_exceptions.ClientConnectorError:
            logger.critical('Request connection error, page: {0}, url: {1}'.format(page_number, self._uri))

        except client_exceptions.ClientOSError:
            logger.critical('Request connection reset, page: {0}, url: {1}'.format(page_number, self._uri))

        except client_exceptions.ServerDisconnectedError:
            logger.critical('Server refused the request, page: {0}, url: {1}'.format(page_number, self._uri))

    async def _get_first_page(self) -> None:
        """ Get first _products page for number of pages """

        self._pages.append(etree.fromstring(await self._request(), self._parser))

        try:
            self._pages_number = int(self._pages[0].xpath(r'//ul[@class="a-pagination"]/li[6]/text()')[0])

        except (IndexError, ValueError) as e:
            logger.critical('Getting pages number failed, error: {}'.format(e))

    async def _send_requests(self) -> None:
        """ Gather _products lists pages via GET requests """

        for response in await asyncio.gather(*[self._request(page) for page in range(self._pages_number + 1)],
                                             return_exceptions=True):
            if isinstance(response, str):
                self._pages.append(etree.fromstring(response, self._parser))

            else:
                logger.warning('Getting item info error: {}'.format(response))

    def _run_loop(self) -> None:
        """ Run ioloop and wait until all requests will be done """

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._session = ClientSession(headers=self._headers, timeout=self._timeout)

        try:
            loop.run_until_complete(self._get_first_page())

            if self._pages_number is None:
                return

            elif self._pages_number > 1:
                loop.run_until_complete(self._send_requests())

        finally:
            loop.run_until_complete(self._session.close())
            loop.close()

    def _find_products_info(self, tree: etree) -> None:
        """ Find necessary _products info in html elements """

        products = tree.xpath('//div[@data-asin]')

        if not len(products):
            logger.warning('Empty _products list before finding info')
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

    def _process_pages(self) -> None:
        """ Process previously found pages """

        if not len(self._pages):
            logger.critical('Pages list is empty')
            return

        for page in self._pages:
            self._find_products_info(page)

    def _get_prices(self) -> None:
        """ Receive lowest prices for _products """

        for price in get_item_price_info(list(self._products.keys()), logger):
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
        """ Find and analyze Amazon _products statistics """

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
