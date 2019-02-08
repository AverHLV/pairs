from django.db import models
from django.contrib.postgres.fields import JSONField
from users.models import CustomUser
from config import constants
from utils import ebay_trading_api, logger


shipping_info_fields = (
    'Name', 'AddressLine1', 'AddressLine2', 'AddressLine3', 'City', 'County', 'District', 'StateOrRegion', 'PostalCode',
    'CountryCode', 'Phone', 'AddressType'
)


class TimeStamped(models.Model):
    """ An abstract base class model that provides self updating """

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class Pair(TimeStamped):
    """ Model for Amazon-eBay ids pair """

    checked = models.PositiveSmallIntegerField(default=0)
    owner = models.ForeignKey(CustomUser, on_delete=models.SET(constants.owner_on_delete_id))
    asin = models.CharField(max_length=constants.asin_length)
    seller_sku = models.CharField(blank=True, max_length=constants.sku_length)
    ebay_ids_length = (constants.ebay_ids_max_count * constants.ebay_id_length) + constants.ebay_ids_max_count - 1
    ebay_ids = models.CharField(max_length=ebay_ids_length)
    quantity = models.PositiveIntegerField(blank=True, null=True)
    amazon_approximate_price = models.FloatField()
    reason_message = models.CharField(max_length=constants.reason_message_max_length, blank=True)
    objects = models.Manager()

    class Meta:
        db_table = 'pairs'

    def __str__(self):
        return str(self.asin)

    def check_quantity(self):
        """ Update item quantity by eBay quantity value """

        quantity = 0

        for ebay_id in str(self.ebay_ids).split(';'):
            if not ebay_trading_api.check_calls(False, print, 'eBay api calls number is over.'):
                break

            else:
                try:
                    response = ebay_trading_api.api.execute('GetItem', {'ItemID': ebay_id})

                    if response.reply.Item.SellingStatus.ListingStatus == 'Active':
                        id_q = int(response.reply.Item.Quantity) - int(response.reply.Item.SellingStatus.QuantitySold)
                    else:
                        id_q = 0

                    quantity += id_q

                except ebay_trading_api.connection_error as e:
                    logger.critical('eBay api unhandled error: {0}.'.format(e.response.dict()))
                    return

        self.quantity = quantity


class Order(TimeStamped):
    """ Amazon order model """

    order_id = models.CharField(max_length=constants.order_id_length)
    purchase_date = models.DateField()
    amazon_price = models.FloatField(default=0)
    ebay_price = models.FloatField(default=0)
    total_profit = models.FloatField(default=0)
    items = models.ManyToManyField(Pair)
    multi = models.BooleanField(default=False)
    owners_profits = JSONField(null=True, blank=True)
    shipping_info = JSONField(null=True, blank=True)
    all_set = models.BooleanField(default=False)
    returned = models.BooleanField(default=False)
    objects = models.Manager()

    class Meta:
        db_table = 'orders'

    def __str__(self):
        return str(self.order_id)

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
