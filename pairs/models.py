import logging
from django.db import models
from django.contrib.postgres.fields import JSONField
from requests.adapters import ConnectionError
from users.models import CustomUser
from config import constants
from utils import ebay_trading_api
from .parsers import get_ebay_quantity_from_response

shipping_info_fields = (
    'Name', 'AddressLine1', 'AddressLine2', 'AddressLine3', 'City', 'County', 'District', 'StateOrRegion', 'PostalCode',
    'CountryCode', 'Phone', 'AddressType'
)

logger = logging.getLogger('custom')


class OrdersManager(models.Manager):
    @staticmethod
    def user_orders(username):
        """ Return orders where the user owns the item """

        orders = Order.objects.all()
        unnecessary_orders_ids = [order.id for order in orders if username not in order.get_owners_names()]
        return orders.exclude(id__in=unnecessary_orders_ids)


class TimeStamped(models.Model):
    """ An abstract base class model that provides self updating """

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class Pair(TimeStamped):
    """
    Model for Amazon-eBay ids pair

    :field checked: pair check status, can be set by moderator, staff user
        or automatically within amazon_workflow task

        possible values:
            0: yet not checked;
            1: checked, all fine;
            2: unsuitable, different items;
            3: unsuitable, different package contain;
            4: unsuitable, cannot be added to the Amazon inventory;
            5: unsuitable, custom reason;
            6: unsuitable, closed by pair owner.

    :field owner: pair owner, provides by CustomUser model
    :field asin: Amazon standard identification number
    :field seller_sku: stock keeping unit, an identification code for a store or product
    :field ebay_ids: string with an eBay identification numbers, delimited by ';'
    :field quantity: sum of the available quantities of all items on eBay

    :field amazon_approximate_price: price for a new product on Amazon, calculated by formulas:
        max: price = ebay_price * ebay_price related interval coeff / profit percentage;
        amazon_approximate_price = max price * max price between eBay items * max price between eBay items coeff

    :field amazon_minimum_price: minimum possible price for item on Amazon, calculated by formulas:
        min: price = ebay_price * ebay_price related interval coeff / profit percentage;
        amazon_minimum_price = ebay_price * price related interval / profit percentage

    :field amazon_current_price: current item price on Amazon
    :field is_buybox_winner: indicates if pair win the buybox or not, also False for no-buybox pairs
    :field old_buybox_price: competitor buybox price, stored for repricing strategy
    :field reason message: custom message with reason of unsuitable check

    """

    checked = models.PositiveSmallIntegerField(default=0)
    owner = models.ForeignKey(CustomUser, on_delete=models.SET(constants.owner_on_delete_id))
    asin = models.CharField(max_length=constants.asin_length)
    seller_sku = models.CharField(blank=True, max_length=constants.sku_length)
    ebay_ids_length = (constants.ebay_ids_max_count * constants.ebay_id_length) + constants.ebay_ids_max_count - 1
    ebay_ids = models.CharField(max_length=ebay_ids_length)
    quantity = models.PositiveIntegerField(blank=True, null=True)
    amazon_approximate_price = models.FloatField()
    amazon_minimum_price = models.FloatField()
    amazon_current_price = models.FloatField(default=0)
    is_buybox_winner = models.BooleanField(default=False)
    old_buybox_price = models.FloatField(default=0)
    reason_message = models.CharField(max_length=constants.reason_message_max_length, blank=True)

    class Meta:
        db_table = 'pairs'

    def __str__(self):
        return self.asin

    def set_buybox_status(self, status, commit=True):
        self.is_buybox_winner = status

        if commit:
            self.save(update_fields=['is_buybox_winner'])

    def check_quantity(self):
        """ Update item quantity by eBay quantity value """

        quantity = 0

        for ebay_id in str(self.ebay_ids).split(';'):
            if not ebay_trading_api.check_calls(False, print, 'eBay api calls number is over.'):
                break

            else:
                try:
                    response = ebay_trading_api.api.execute('GetItem', {'ItemID': ebay_id})

                except ebay_trading_api.connection_error as e:
                    logger.critical('eBay ID: {0}, eBay api unhandled error: {1}.'.format(ebay_id, e.response.dict()))
                    return

                except ConnectionError:
                    logger.critical('Remote end closed connection without response from eBay.')
                    return

                quantity += get_ebay_quantity_from_response(response)

        self.quantity = quantity


class Order(TimeStamped):
    """
    Amazon order model

    :field order_id: Amazon order unique identifier
    :field purchase date: order purchase date
    :field amazon_price: order total price on Amazon
    :field ebay_price: order total price on eBay
    :field total_profit: clean income from this order
    :field items: order items, provides by Pair model
    :field multi: is order contains one item or many

    :field items_counts: dictionary with items counts from this order in format:
        item.id: count

    :field owners_profits: dictionary with owners profits in format:
        owner.username: profit

    :field shipping info: dictionary with order shipping info from Amazon customer
        possible keys (according to mws response):
            Name          - customer name (include first and last name);
            AddressType   - indicates whether the address is commercial or residential,
                            this element is used only in the US marketplace;
            AddressLine1  - street address;
            AddressLine2  - additional street address information, if required;
            AddressLine3  - additional street address information, if required;
            City          - city;
            County        - county;
            CountryCode   - country code;
            District      - district;
            PostalCode    - postal code;
            Phone         - phone number;
            StateOrRegion - state or region (can be like abbreviation or full name).

    :field all_set: boolean, indicates is order purchased or not,
        purchase information can be added manually by moderator or automatically by make_purchases task

    :field returned: boolean, indicates is order was returned or not

    :field items_buying_status: dictionary with automatic purchase results, format:
        item.asin: False                    - if purchase task failed before buying on eBay;
                   {ebay_id: True or False} - dictionary with item ebay_ids and their purchase results.
    """

    order_id = models.CharField(max_length=constants.order_id_length)
    purchase_date = models.DateField()
    amazon_price = models.FloatField(default=0)
    ebay_price = models.FloatField(default=0)
    total_profit = models.FloatField(default=0)
    items = models.ManyToManyField(Pair)
    multi = models.BooleanField(default=False)
    items_counts = JSONField()
    owners_profits = JSONField(null=True, blank=True)
    shipping_info = JSONField(null=True, blank=True)
    all_set = models.BooleanField(default=False)
    returned = models.BooleanField(default=False)
    items_buying_status = JSONField(null=True, blank=True)
    objects = OrdersManager()

    class Meta:
        db_table = 'orders'

    def __str__(self):
        return self.order_id

    def get_items(self):
        return self.items.all()

    def get_owners(self):
        return list(set([item.owner for item in self.get_items()]))

    def get_first_owner(self):
        return self.get_owners()[0]

    def get_owners_names(self):
        return [owner.username for owner in self.get_owners()]

    def set_profits(self, dictionary, commit=True):
        """ Update owners profits by dictionary like 'owner: profit' """

        self.owners_profits = dictionary
        
        if commit:
            self.save(update_fields=['owners_profits'])

    def set_multi(self):
        """ Check whether it is a multi-order """

        if len(self.get_owners()) > 1:
            self.multi = True
            self.save(update_fields=['multi'])

    def calculate_profits(self, owner=None):
        """
        Calculate profits for all owners, there must be
        either one owner, or all benefits of the owners must be indicated
        """

        if not self.multi and self.all_set:
            result = [(list(self.owners_profits.keys())[0], self.owners_profits[list(self.owners_profits.keys())[0]])]

            if owner:
                return result[0][1]

            return result

        elif self.all_set:
            if owner:
                return self.owners_profits[owner]

            return [(owner, self.owners_profits[owner]) for owner in self.owners_profits.keys()]


class NotAllowedSeller(models.Model):
    """ Model for not allowed seller from eBay """

    ebay_user_id = models.CharField(max_length=constants.na_seller_id_length)
    objects = models.Manager()

    def __str__(self):
        return self.ebay_user_id
