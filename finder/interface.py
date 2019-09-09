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
from pairs.parsers import parse_delivery_time_response
from decorators import log_work_time
from utils import secret_dict

logger = logging.getLogger('finder')


class AmazonFinder(object):
    """ Amazon products information finder """

    _headers = {'Connection': 'close'}
    _parser = etree.HTMLParser()
    _timeout = ClientTimeout(total=constants.timeout)
    _ebay_uri = 'https://www.ebay.com/sch/i.html'
    _ebay_item_uri = 'https://www.ebay.com/itm/'
    _ebay_params = {'_nkw': '', '_ipg': 100, 'LH_BIN': 1, 'LH_ItemCondition': 3, 'LH_PrefLoc': 1, 'LH_RPA': 1}
    _proxy_uri = 'https://proxy11.com/api/proxy.txt?key={}&country=United+States'

    def __init__(self, uri: str = None, use_proxy: bool = False, proxy_tries: int = constants.proxy_find_tries):
        """
        AmazonFinder initialization

        :param uri: Amazon search uri
        :param use_proxy: use proxy for requests to Amazon or not
        :param proxy_tries: number of tries to find alive proxy
        """

        if uri is None:
            return

        self._session = None
        self._pages_number = None
        self._proxy = None
        self._asins = []
        self._products = {}

        self._use_proxy = use_proxy

        if self._use_proxy:
            self._proxy_uri = self._proxy_uri.format(secret_dict['proxy_api_key']) + '&limit={}'.format(proxy_tries)

        self._amazon_uri = sub(r'&page=\d+', '', uri) + '&page={page_number}'

    @log_work_time('AmazonFinder')
    def __call__(self, *args, **kwargs) -> dict:
        """ Reinitialize for new uri and find products info """

        self.__init__(*args, **kwargs)
        self._run_loop()
        self._asins = list(self._products.keys())

        if not len(self._asins):
            logger.critical('Empty asins list after getting Amazon info')
            return {}

        logger.info('All items number: {}'.format(len(self._asins)))
        self._run_loop(send_type='ebay')

        if not len(self._asins):
            logger.critical('No asins for getting delivery times')
            return {}

        self._run_loop(send_type='delivery')

        if not len(self._asins):
            logger.critical('No asins for getting prices')
            return {}

        self._get_prices()
        logger.info('Amazon: final items number: {}'.format(len(self._asins)))

        return self._products

    async def _request(self,
                       uri: str,
                       search_term: str = None,
                       params: dict = None,
                       proxy: str = None,
                       delay: bool = False) -> str:
        """
        Send GET request

        :param uri: request uri
        :param search_term: uri parameters
        :param params: uri parameters
        :param proxy: request proxy
        :param delay: add async sleep before request
        :return: html str response
        """

        if delay:
            await asyncio.sleep(constants.request_delay)

        if search_term is not None:
            self._ebay_params['_nkw'] = search_term
            params = self._ebay_params

        try:
            async with self._session.get(uri, params=params, proxy=proxy) as response:
                return await response.text()

        except client_exceptions.ServerTimeoutError:
            logger.critical('Request timeout error, url: {}'.format(uri))

        except client_exceptions.ClientConnectorError as e:
            logger.critical('Request connection error: {0}, url: {1}'.format(e, uri))

        except client_exceptions.ClientOSError:
            logger.critical('Request connection reset, url: {}'.format(uri))

        except client_exceptions.InvalidURL as e:
            logger.critical('Invalid url: {}'.format(e))

        except client_exceptions.ServerDisconnectedError:
            logger.critical('Server refused the request, url: {}'.format(uri))

        except client_exceptions.ClientHttpProxyError as e:
            self._proxy = None
            logger.critical('Proxy response error, disabling proxy, error: {}'.format(e))

    async def _find_proxy(self) -> None:
        """ Find proxy and check aliveness """

        proxies = await self._request(self._proxy_uri)

        if proxies is None:
            logger.warning('AmazonFinder: getting proxy failed')

        for proxy in proxies.split('\n'):
            self._proxy = 'http://' + proxy
            await self._get_first_page()

            if self._pages_number is not None:
                logger.info('Proxy works fine! Url: {}'.format(self._proxy))
                break

        else:
            logger.critical('Getting alive proxy failed')

    async def _get_first_page(self) -> None:
        """ Get first products page for number of pages """

        response = await self._request(self._amazon_uri.format(page_number=1), proxy=self._proxy)

        if response is None:
            logger.critical('Getting pages number failed while first request')
            return

        page = etree.fromstring(response, self._parser)
        self._find_products_info(page)

        try:
            self._pages_number = int(page.xpath(r'//ul[@class="a-pagination"]/li[6]/text()')[0])

        except (IndexError, ValueError) as e:
            logger.critical('Getting pages number failed, parse error: {}'.format(e))

    async def _send_requests(self, send_type: str) -> None:
        """
        Gather products lists pages via GET requests

        :param send_type: send requests type:
            amazon - Amazon search uri
            ebay - eBay search
            delivery - eBay delivery time
        """

        # make requests

        if send_type == 'amazon':
            responses = await asyncio.gather(
                *[self._request(self._amazon_uri.format(page_number=page), proxy=self._proxy, delay=True)
                  for page in range(self._pages_number + 1)],
                return_exceptions=True
            )

        elif send_type == 'ebay':
            responses = await asyncio.gather(
                *[self._request(self._ebay_uri, search_term=self._products[asin]['title'], delay=True)
                  for asin in self._asins],
                return_exceptions=True
            )

        else:
            ebay_ids = []

            for asin in self._asins:
                ebay_ids += self._products[asin]['ebay_ids']

            responses = await asyncio.gather(
                *[self._request(self._ebay_item_uri + ebay_id, delay=True) for ebay_id in ebay_ids],
                return_exceptions=True
            )

        # parse responses

        values_to_delete = []

        if send_type != 'delivery':
            for i in range(len(responses)):
                if isinstance(responses[i], str):
                    page = etree.fromstring(responses[i], self._parser)

                    if send_type == 'amazon':
                        self._find_products_info(page)

                    else:
                        ebay_ids = self._find_ebay_products_info(page)

                        if ebay_ids is not None:
                            self._products[self._asins[i]]['ebay_ids'] = ebay_ids

                        else:
                            self._products.pop(self._asins[i])
                            values_to_delete.append(self._asins[i])

                else:
                    if send_type == 'ebay':
                        self._products.pop(self._asins[i])
                        values_to_delete.append(self._asins[i])

                    logger.warning('Getting item info error: {}'.format(responses[i]))

        else:
            i = 0

            for asin in self._asins:
                # check all ebay ids for one asin

                ebay_ids_to_delete = []

                for ebay_id_number, response in enumerate(responses[i:i + len(self._products[asin]['ebay_ids'])]):
                    if isinstance(response, str):
                        delivery_date = parse_delivery_time_response(etree.fromstring(response, self._parser))

                        if delivery_date is not None and delivery_date >= constants.ebay_max_delivery_time:
                            ebay_ids_to_delete.append(self._products[asin]['ebay_ids'][ebay_id_number])

                    else:
                        ebay_ids_to_delete.append(self._products[asin]['ebay_ids'][ebay_id_number])

                if len(ebay_ids_to_delete):
                    for value in ebay_ids_to_delete:
                        self._products[asin]['ebay_ids'].remove(value)

                # delete asin if all ebay ids did not pass the test

                if not len(self._products[asin]['ebay_ids']):
                    self._products.pop(asin)
                    values_to_delete.append(asin)

                i += len(self._products[asin]['ebay_ids'])

        # delete asins

        if len(values_to_delete):
            for value in values_to_delete:
                self._asins.remove(value)

    def _run_loop(self, send_type: str = 'amazon') -> None:
        """ Run ioloop and wait until all requests will be done """

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._session = ClientSession(headers=self._headers, timeout=self._timeout)

        try:
            if send_type == 'amazon':
                if self._use_proxy:
                    loop.run_until_complete(self._find_proxy())

                # start sending requests

                if self._pages_number is None:
                    loop.run_until_complete(self._get_first_page())

                if self._pages_number is None:
                    return

                if self._pages_number > 1:
                    loop.run_until_complete(self._send_requests(send_type))

            else:
                loop.run_until_complete(self._send_requests(send_type))

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
