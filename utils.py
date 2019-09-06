from ebaysdk.trading import Connection as Trading
from ebaysdk.shopping import Connection as Shopping
from ebaysdk.finding import Connection as Finding
from ebaysdk.exception import ConnectionError
from mws import Products, Orders, Feeds, MWSError
from django.core.exceptions import ImproperlyConfigured

from xml.etree import ElementTree
from copy import deepcopy
from datetime import datetime, timedelta
from time import sleep
from json import loads

from config import constants


def get_secret(filename):
    """ Get the secret from json file or raise exception """

    fields = (
        'secret_key', 'db_admin', 'db_pass', 'db_name', 'db_host', 'db_port', 'broker_url', 'em_user', 'em_pass',
        'em_server', 'em_port', 'eb_app_id', 'eb_dev_id', 'eb_cert_id', 'eb_ru_name', 'eb_user_token',
        'eb_token_exp_date', 'eb_username', 'eb_password', 'pp_email', 'pp_password', 'am_seller_id', 'am_access_key',
        'am_secret_key', 'am_auth_token', 'keepa_key', 'hosts', 'admins'
    )

    try:
        with open(filename) as secret:
            secret = loads(secret.read())

        return {field: secret[field] for field in fields}

    except IOError:
        raise ImproperlyConfigured('Specified file does not exists: {0}'.format(filename))

    except KeyError as k:
        raise ImproperlyConfigured('Add the {0} field to json secret'.format(k))


class ApiCallsChecker(object):
    """ Class for check and update ability to make api requests with limits per time period """

    def __init__(self, service):
        self.__status = True
        self.__start_time = datetime.now()
        self.__service = service
        self.__counter = 0

        if self.__service == 'ebay-trading':
            self.__calls_limit = constants.ebay_trading_api_calls_number

        elif self.__service == 'amazon-products':
            self.__calls_limit = constants.amazon_product_api_calls_number

        else:
            self.__calls_limit = None

    def update_counter(self):
        self.__counter += 1

        if self.__calls_limit is not None and self.__counter > self.__calls_limit:
            self.__status = False

    def update_status(self):
        self.__status = True
        self.__start_time = datetime.now()

    @property
    def status(self):
        return self.__status

    @property
    def start_time(self):
        if self.__service == 'ebay-trading':
            return '{0}:{1}'.format(self.__start_time.hour, self.__start_time.minute)

        elif self.__service == 'amazon-products':
            return '{0}:{1}'.format((self.__start_time + timedelta(hours=1)).hour, self.__start_time.minute)


class ApiObject(object):
    """ Class that represents connection and calls limit checking for specified api """

    def __init__(self, secret, service, tries=constants.con_tries, delay=constants.con_delay, country=None,
                 feed_types=None):
        self.__tries = tries
        self.__init_tries = tries
        self.__delay = delay
        self.__region = country
        self.__feed_types = feed_types
        self.__connection_error = None
        self.__api = None
        self.connector(secret, service)
        self.checker = None

    @property
    def api(self):
        return self.__api

    @property
    def connection_error(self):
        return self.__connection_error

    @property
    def region(self):
        return self.__region

    @property
    def feed_types(self):
        return self.__feed_types

    def connector(self, secret, service):
        """ Get connection to specified api """

        if service[:4] == 'ebay':
            self.__connection_error = ConnectionError

            if datetime.strptime(secret['eb_token_exp_date'], '%Y-%m-%d %H:%M:%S') <= datetime.now():
                raise ValueError('User token expired! Expiration date: {0}'.format(secret['eb_token_exp_date']))

            if service == 'ebay-trading':
                api = Trading

            elif service == 'ebay-shopping':
                api = Shopping

            elif service == 'ebay-finding':
                api = Finding

            else:
                raise ValueError('This eBay api is not supported: {0}'.format(service))

            def get_connection():
                return api(appid=secret['eb_app_id'], devid=secret['eb_dev_id'], certid=secret['eb_cert_id'],
                           token=secret['eb_user_token'], config_file=None)

        elif service[:6] == 'amazon':
            if self.__region is None:
                raise ValueError('Please, set a marketplace country.')

            try:
                region_info = constants.amazon_market_ids[self.__region]

            except KeyError:
                raise ValueError('Region info for specified country ({0}) does not exist.'.format(self.__region))

            self.__region = region_info['id']
            self.__connection_error = MWSError

            if service == 'amazon-products':
                api = Products

            elif service == 'amazon-orders':
                api = Orders

            elif service == 'amazon-feeds':
                api = Feeds

            else:
                raise ValueError('This Amazon api is not supported: {0}'.format(service))

            def get_connection():
                return api(secret['am_access_key'], secret['am_secret_key'], secret['am_seller_id'],
                           auth_token=secret['am_auth_token'], region=region_info['code'])

        else:
            raise ValueError('This api is not supported: {0}'.format(service))

        while self.__tries:
            try:
                api = get_connection()

            except self.__connection_error as e:
                self.__tries -= 1
                sleep(self.__delay)

                if not self.__tries:
                    raise ValueError('Connection error: {0}, after {1} tries.'.format(e, self.__tries))

            else:
                self.__tries = self.__init_tries
                self.__api = api
                break

    def check_calls(self, exception, func, *func_args, **func_kwargs):
        if self.checker is None:
            return True

        if not self.checker.status:
            if exception:
                raise func(*func_args, **func_kwargs)
            else:
                func(*func_args, **func_kwargs)
                return False

        self.checker.update_counter()
        return True


class XmlHelper(object):
    """ Class for request body creation in xml format """

    def __init__(self, path, merchant_id, message_type):
        self.__message_number = 1
        self.__message_type = message_type
        self.__path = path
        self.__merchant_id = merchant_id
        self.__tree = ElementTree.parse(self.__path[0])
        self.__tree.find('.//MerchantIdentifier').text = self.__merchant_id

        try:
            self.__tree.find('.//MessageType').text = constants.amazon_message_types[self.__message_type]

        except KeyError:
            raise ValueError('Wrong message type: {0}'.format(self.__message_type))

        self.__root = self.__tree.getroot()
        self.__message = ElementTree.parse(self.__path[1]).getroot()

    @property
    def tree(self):
        return ElementTree.tostring(self.__root, encoding='utf-8', method='xml')

    def save_tree(self, filename):
        self.__tree.write(filename)

    def reload_tree(self):
        self.__message_number = 1
        self.__tree = ElementTree.parse(self.__path[0])
        self.__tree.find('.//MerchantIdentifier').text = self.__merchant_id
        self.__tree.find('.//MessageType').text = constants.amazon_message_types[self.__message_type]
        self.__root = self.__tree.getroot()
        self.__message = ElementTree.parse(self.__path[1]).getroot()

    def add_message(self, sku, param=None):
        if param is None and self.__message_type != 'delete_product':
            raise ValueError('Second argument should be not None')

        message = deepcopy(self.__message)
        message.find('.//MessageID').text = str(self.__message_number)
        message.find('.//SKU').text = sku

        if self.__message_type == 'quantity':
            if not str(param).isdigit():
                raise ValueError('Quantity value must be integer only')

            message.find('.//Quantity').text = str(param)

        elif self.__message_type == 'product':
            message.find('.//Value').text = str(param)

        elif self.__message_type == 'price':
            try:
                float(param)

            except ValueError:
                raise ValueError('Price value must be float or integer only')

            message.find('.//StandardPrice').text = str(param)

        self.__root.insert(self.__message_number + 1, message)
        self.__message_number += 1

    def make_body(self, messages):
        for message in messages:
            self.add_message(*message)


# specific info
secret_dict = get_secret(constants.secret_filename)

# apis
ebay_trading_api = ApiObject(secret_dict, 'ebay-trading')
ebay_shopping_api = ApiObject(secret_dict, 'ebay-shopping')
amazon_products_api = ApiObject(secret_dict, 'amazon-products', country=constants.amazon_region)
amazon_orders_api = ApiObject(secret_dict, 'amazon-orders', country=constants.amazon_region)
amazon_feeds_api = ApiObject(secret_dict, 'amazon-feeds', feed_types=constants.amazon_feed_types,
                             country=constants.amazon_region)

# helpers
xml_quantity_helper = XmlHelper((constants.xml_header_filename, constants.xml_message_quantity_filename),
                                secret_dict['am_seller_id'], message_type='quantity')
xml_product_helper = XmlHelper((constants.xml_header_filename, constants.xml_message_product_filename),
                               secret_dict['am_seller_id'], message_type='product')
xml_price_helper = XmlHelper((constants.xml_header_filename, constants.xml_message_price_filename),
                             secret_dict['am_seller_id'], message_type='price')
xml_delete_product_helper = XmlHelper((constants.xml_header_filename, constants.xml_message_delete_product_filename),
                                      secret_dict['am_seller_id'], message_type='delete_product')
