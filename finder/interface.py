import logging
import asyncio

from aiohttp import client_exceptions, ClientSession, ClientTimeout
from django.core.exceptions import ImproperlyConfigured
from keepa import Keepa
from browseapi import BrowseAPI
from lxml import etree
from numpy import isnan

from base64 import b64encode
from datetime import datetime, timedelta
from re import sub

from config import constants
from decorators import log_work_time

logger = logging.getLogger('finder')


class AmazonFinder(object):
    """ Amazon products finder """

    def __init__(self, url=None):
        """
        AmazonFinder initialization

        :param url: Amazon search url, str
        """

        if url is None:
            return

        self.session = None
        self.pages_number = None
        self.pages = []
        self.products = {}
        self.url = url + '&page={page_number}'
        self.headers = {'Connection': 'close'}
        self.parser = etree.HTMLParser()

    @log_work_time('AmazonFinder')
    def __call__(self, url: str) -> dict:
        """ Reinitialize for new url and find products info """

        self.__init__(url)
        self.run_loop()
        self.process_pages()
        return self.products

    async def request(self, page_number=1, url=None):
        """
        Send GET request

        :param page_number: positive integer
        :param url: url for image downloading
        :return: html response in bytes or str
        """

        image = True

        if url is None:
            url = self.url.format(page_number=page_number)
            image = False

        try:
            async with self.session.get(url) as response:
                if not image:
                    return await response.text()
                else:
                    return await response.read()

        except client_exceptions.ServerTimeoutError:
            logger.critical('Request timeout error, page: {0}, url: {1}'.format(page_number, url))

        except client_exceptions.ClientConnectorError:
            logger.critical('Request connection error, page: {0}, url: {1}'.format(page_number, url))

        except client_exceptions.ClientOSError:
            logger.critical('Request connection reset, page: {0}, url: {1}'.format(page_number, url))

        except client_exceptions.ServerDisconnectedError:
            logger.critical('Server refused the request, page: {0}, url: {1}'.format(page_number, url))

    async def get_first_page(self) -> None:
        """ Get first products page for number of pages """

        self.session = ClientSession(headers=self.headers, timeout=ClientTimeout(total=constants.timeout))

        try:
            self.pages.append(etree.fromstring(await self.request(), self.parser))
            self.pages_number = int(self.pages[0].xpath(r'//ul[@class="a-pagination"]/li[6]/text()')[0])

        finally:
            await self.session.close()

    async def send_requests(self) -> None:
        """ Gather products lists pages via GET requests """

        self.session = ClientSession(headers=self.headers, timeout=ClientTimeout(total=constants.timeout))

        try:
            responses = await asyncio.gather(*[self.request(page) for page in range(self.pages_number + 1)],
                                             return_exceptions=True)

            for response in responses:
                if isinstance(response, str):
                    self.pages.append(etree.fromstring(response, self.parser))

                else:
                    logger.warning('Getting item info error: {}'.format(response))

        finally:
            await self.session.close()

    async def load_images(self) -> None:
        """ Load and encode images for all products """

        self.session = ClientSession(headers=self.headers, timeout=ClientTimeout(total=constants.timeout))

        try:
            products = [(product, self.products[product]['url']) for product in self.products]

            responses = await asyncio.gather(
                *([self.request(url=product[1]) for product in products]),
                return_exceptions=True
            )

            for i in range(len(responses)):
                if isinstance(responses[i], bytes):
                    self.products[products[i][0]]['img'] = str(b64encode(responses[i])[2:-1])

                else:
                    logger.warning('Getting item picture error: {}'.format(responses[i]))

        finally:
            await self.session.close()

    def run_loop(self) -> None:
        """ Run ioloop and wait until all requests will be done """

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # loop.run_until_complete(self.get_first_page())
            self.pages_number = 25

            if self.pages_number is None:
                logger.critical('Getting pages number failed')

            elif self.pages_number > 1:
                loop.run_until_complete(self.send_requests())

        finally:
            loop.close()

    @log_work_time('AmazonFinder: images')
    def run_loop_for_images(self, products: dict) -> dict:
        """ Run ioloop and wait until all images will be downloaded """

        self.products = products

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self.load_images())

        finally:
            loop.close()

        return self.products

    def find_products_info(self, tree: etree) -> None:
        """ Find necessary products info in html elements """

        products = tree.xpath('//div[@data-asin]')

        if not len(products):
            logger.warning('Empty products list before finding')
            return

        for product in products:
            img = product.xpath('.//img')[0]
            asin = product.get('data-asin')
            url = img.get('src')
            title = img.get('alt')

            if len(asin) != constants.asin_length:
                asin = None

            if title is not None:
                title = sub(r'[^0-9a-z ]', '', title.lower())
                title = sub(r' {2,}', ' ', ' ' + title + ' ')
                title = sub(r' ({0}) '.format('|'.join(constants.stopwords)), ' ', title)
                title = sub(r'^ | $', '', title)
                title = ' '.join(title.split()[:constants.title_n_words])
                title = sub(r' ', ',', title)

            else:
                title = None

            for value in asin, url, title:
                if value is None or not len(value):
                    break

            else:
                self.products[asin] = {'url': url, 'title': title}

    def process_pages(self) -> None:
        """ Process previously found pages """

        if not len(self.pages):
            raise ValueError('Pages list is empty')

        for page in self.pages:
            self.find_products_info(page)


class KeepaFinder(object):
    """ Keepa API client for finding and analyzing product information """

    def __init__(self, secret_key: str):
        """
        KeepaFinder initialization

        :param secret_key: 64 character secret key
        """

        try:
            self.api = Keepa(secret_key)

        except Exception:
            # no custom exception in keepa interface for this case

            raise ImproperlyConfigured('Invalid Keepa API secret key')

    @log_work_time('KeepaFinder')
    def __call__(self, products: dict) -> dict:
        """ Find and analyze Amazon products statistics """

        self.products = {}
        self.products_history(list(products.keys()))

        for asin in self.products:
            if not self.products[asin]['amazon'] or not self.analyze_sales(self.products[asin]['sales']) or \
                    not self.analyze_offers(self.products[asin]['offers']):
                products.pop(asin)

        return products

    def products_history(self, asins: list) -> None:
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

            self.products[asins[product_index]] = {
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
            if sales[i] - sales[i + 1] >= constants.rank_drop:
                drop_number += 1

        if drop_number >= constants.threshold_month_number:
            return True

        return False


if __name__ == '__main__':
    from json import loads

    try:
        with open('finder_secret.json') as file:
            secret = loads(file.read())

    except IOError as ex:
        secret = None
        print('Secret file not found: {0}'.format(ex))
        exit()

    am_finder = AmazonFinder()
    api = BrowseAPI(secret['eb_app_id'], secret['eb_cert_id'])
    info = am_finder('https://www.amazon.com/s?me=A193OK6W10JJDU&marketplaceID=ATVPDKIKX0DER')

    # keepa_finder = KeepaFinder(secret['secret_key'])
    # info_results = keepa_finder(info)

    info_results = am_finder.run_loop_for_images(info)
    asin_info = list(info_results.keys())

    resps = api.execute('search', [{'q': info_results[asin]['title']} for asin in asin_info])

    for k in range(len(asin_info)):
        print('ASIN:', asin_info[k])
        print('Q:', info_results[asin_info[k]]['title'])

        try:
            for j in range(5):
                print(resps[k].itemSummaries[j].itemId.split('|'))
                print(resps[k].itemSummaries[j].title, '\n')

        except (IndexError, AttributeError):
            print('None\n')
            continue

        print('\n')
