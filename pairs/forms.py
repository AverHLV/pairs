from django import forms
from re import search
from requests.adapters import ConnectionError
from config import constants
from utils import ebay_trading_api, amazon_products_api, logger
from .helpers import get_item_price_info
from .parsers import get_rank_from_response, get_delivery_time, get_ebay_price_from_response
from .models import Pair


class PairForm(forms.ModelForm):
    """ Creating and updating form for Pair model """

    class Meta:
        model = Pair
        fields = 'asin', 'ebay_ids'

    def __init__(self, old_data=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.amazon_price = 0
        self.amazon_minimum_price = 0
        self.amazon_approximate_price = 0
        self.ebay_price = []
        self.old_data = old_data
        self.old_asin_not_changed = False
        self.old_ebay_not_changed = False
        self.variated_item = False  # TODO: check behaviour with this items
        self.sku = None

        self.fields['asin'].label = 'ASIN'
        self.fields['ebay_ids'].label = 'eBay ids'

        self.fields['asin'].help_text = '''
                                        <ul>
                                            <li>Required.</li>
                                            <li>Possible length: {0}.</li>
                                            <li>Item sales rank should be lower or equal than {1}.</li>
                                        </ul>
                                        
                                        The minimum benefit from the item should be no less than the Amazon price 
                                        minus {2}$. 
                                        <a href="/profits/" target="_blank">Profits coefficients for all intervals</a>.
                                        '''.format(constants.asin_length, constants.amazon_max_salesrank,
                                                   constants.profit_buffer)

        self.fields['ebay_ids'].help_text = '''
                            <ul>
                                <li>Required.</li>
                                <li>All ids should be unique.</li>
                                <li>Please, split ids by '<b>;</b>' delimiter.</li>
                                <li>Don’t put delimiter after last id.</li>
                                <li>One id length: {0}.</li>
                                <li>Maximum ids count: {1}.</li>
                                <li>Seller should accepts return for all items.</li>
                                <li>Feedback score should be greater than {3}.</li>
                                <li>Positive feedback percentage should be greater than {4}%.</li>
                                <li>High end of delivery time for all items should be lower or equal than {2} days.</li>
                            </ul>
                            
                            For example: 123456789123;987654321987
                            '''.format(constants.ebay_id_length, constants.ebay_ids_max_count,
                                       constants.ebay_max_delivery_time, constants.ebay_min_feedback_score,
                                       constants.ebay_min_positive_percentage)

    def check_profit(self):
        """ Check minimum profit for asin and all eBay ids and calculate approximate price for Amazon """

        prices, ebay_prices = [], []

        for ebay_price in self.ebay_price:
            if not ebay_price:
                continue

            price = 0

            for interval in constants.profit_intervals:
                if interval[0] <= ebay_price < interval[1]:
                    price = ebay_price * constants.profit_intervals[interval] / constants.profit_percentage
                    prices.append(price)
                    ebay_prices.append(ebay_price)
                    break

            if self.amazon_price:
                if price + constants.profit_buffer >= self.amazon_price:
                    return False

        # getting approximate price

        max_ebay_price_coeff = 0
        max_price = max(prices)
        max_ebay_price = ebay_prices[prices.index(max_price)]

        for interval in constants.amazon_approximate_price_percent:
            if interval[0] <= max_ebay_price < interval[1]:
                max_ebay_price_coeff = constants.amazon_approximate_price_percent[interval]

        self.amazon_minimum_price = round(min(prices), 2)
        self.amazon_approximate_price = round(max_price + max_ebay_price * max_ebay_price_coeff, 2)
        return True

    def clean_input_asin(self):
        asin = self.cleaned_data['asin']

        if self.old_data is not None:
            if asin == self.old_data['asin']:
                self.old_asin_not_changed = True
                return asin

        if len(asin) != constants.asin_length:
            raise forms.ValidationError({'asin': 'ASIN should be {0} length.'.format(constants.asin_length)},
                                        code='am1')

        if search('[^A-Z0-9]', asin):
            raise forms.ValidationError({'asin': 'ASIN should contains only numbers and uppercase letters.'},
                                        code='am2')

        if Pair.objects.filter(asin__exact=asin).exists():
            raise forms.ValidationError({'asin': 'This ASIN already exists.'.format(constants.asin_length)}, code='am4')

        # validation based on api response

        try:
            response = amazon_products_api.api.get_matching_product_for_id(amazon_products_api.region, 'ASIN', [asin])
            response_my_product = amazon_products_api.api.get_my_price_for_asin(amazon_products_api.region, [asin])

        except amazon_products_api.connection_error as e:
            logger.warning(e)
            raise forms.ValidationError({'asin': 'Amazon api unhandled error: {0}.'.format(e)}, code='am5')

        else:
            try:
                if response.parsed['Error']['Code']['value'] == 'InvalidParameterValue':
                    raise forms.ValidationError({'asin': 'Invalid ASIN.'}, code='am6')

                else:
                    error = response.parsed['Error']['Code']['value']
                    logger.warning(error)
                    raise forms.ValidationError({'asin': 'Amazon api unhandled error in response! Error: {0}.'
                                                .format(error)}, code='am5')

            except KeyError:
                pass

            # checking for Amazon sales rank

            rank = get_rank_from_response(response)

            if not rank:
                raise forms.ValidationError({'asin': 'Sales rank is unavailable. Please try later'}, code='am9')

            if rank > constants.amazon_max_salesrank:
                raise forms.ValidationError({'asin': 'Item sales rank is greater than {0}.'
                                            .format(constants.amazon_max_salesrank)}, code='am8')

            # checking for item variations, product existing in inventory and price

            try:
                self.amazon_price = float(response_my_product.parsed['Product']['Offers']['Offer']['BuyingPrice']
                                          ['LandedPrice']['Amount']['value'])

            except (KeyError, ValueError):
                self.amazon_price = get_item_price_info([asin], logger)

                if self.amazon_price is None:
                    raise forms.ValidationError({'asin': 'Getting price from Amazon failed'}, code='am10')

                self.amazon_price = self.amazon_price[0][0]

                if not self.amazon_price:
                    self.variated_item = True

            else:
                self.sku = response_my_product.parsed['Product']['Offers']['Offer']['SellerSKU']['value']

        return asin

    def clean_input_ebay_ids(self):
        old_ebay_ids_to_add = []
        ebay_ids = self.cleaned_data['ebay_ids']

        # in update case

        if self.old_data is not None:
            if ebay_ids == self.old_data['ebay_ids']:
                self.old_ebay_not_changed = True
                return ebay_ids
            else:
                ebay_ids_split = ebay_ids.split(';')

                for ebay_id in self.old_data['ebay_ids'].split(';'):
                    if ebay_id in ebay_ids_split:
                        ebay_ids_split.remove(ebay_id)
                        old_ebay_ids_to_add.append(ebay_id)

                ebay_ids = ';'.join(ebay_ids_split)

        # if user deletes some ids and current ids are old

        if not len(ebay_ids):
            self.variated_item = True
            return ebay_ids + ';'.join(old_ebay_ids_to_add)

        # validation begins

        if search('[^0-9;]', ebay_ids):
            raise forms.ValidationError({'ebay_ids': 'eBay ids should contain only numbers and delimiter.'},
                                        code='eb1')

        if ';' == ebay_ids[-1]:
            raise forms.ValidationError({'ebay_ids': 'Don’t put delimiter after last id.'}, code='eb2')

        if len(ebay_ids) > constants.ebay_id_length and search(';', ebay_ids) is None:
            raise forms.ValidationError({'ebay_ids': "eBay ids delimiter should be ';'."}, code='eb3')

        ebay_ids_split = ebay_ids.split(';')

        if len(ebay_ids_split) > len(set(ebay_ids_split)):
            raise forms.ValidationError({'ebay_ids': 'Your input string contains duplicate ids.'}, code='eb4')

        if len(ebay_ids_split) > constants.ebay_ids_max_count:
            raise forms.ValidationError({
                'ebay_ids': 'Your input string contains more than {0} ids.'.format(constants.ebay_ids_max_count)
            }, code='eb5')

        for ebay_id in ebay_ids_split:
            if len(ebay_id) != constants.ebay_id_length:
                raise forms.ValidationError({
                    'ebay_ids': 'One of your ids has wrong length. eBay id length should be {0}.'
                    .format(constants.ebay_id_length)
                }, code='eb6')

            if Pair.objects.filter(ebay_ids__contains=ebay_id).exists():
                raise forms.ValidationError({'ebay_ids': 'This id ({0}) already exists.'.format(ebay_id)}, code='eb7')

            # validation based on api response

            '''
            ebay_trading_api.check_calls(True, forms.ValidationError,
                                         'eBay api calls number is over. Please try to add pair tomorrow in {0}.'
                                         .format(ebay_trading_api.checker.start_time), code='eb8')
            '''

            try:
                response = ebay_trading_api.api.execute('GetItem', {'ItemID': ebay_id})

            except ConnectionError:
                raise forms.ValidationError({
                    'ebay_ids': 'Remote end closed connection without response from eBay. Please try again.'
                }, code='eb17')

            except ebay_trading_api.connection_error as e:
                if e.response.dict()['Errors']['ErrorCode'] == '17':
                    raise forms.ValidationError({'ebay_ids': 'This id ({0}) is invalid.'.format(ebay_id)}, code='eb9')

                else:
                    logger.warning(e.response.dict()['Errors'])

                    raise forms.ValidationError({
                        'ebay_ids': 'eBay api unhandled error: {0}.'.format(e.response.dict()['Errors'])
                    }, code='eb10')

            else:
                # listing status checking

                if response.reply.Item.SellingStatus.ListingStatus != 'Active':
                    raise forms.ValidationError({
                        'ebay_ids': "Listing status for this item ({0}) is not 'Active'.".format(ebay_id)
                    }, code='eb11')

                if response.reply.Item.ReturnPolicy.ReturnsAcceptedOption == 'ReturnsNotAccepted':
                    raise forms.ValidationError({
                        'ebay_ids': 'Seller does not accept return for this item ({0}).'.format(ebay_id)
                    }, code='eb12')

                # checking seller statistics

                feedback_score = int(response.reply.Item.Seller.FeedbackScore)

                if feedback_score <= constants.ebay_min_feedback_score:
                    raise forms.ValidationError({
                        'ebay_ids': 'Feedback score for this item ({0}) lower or equal than {1}.'
                        .format(ebay_id, constants.ebay_min_feedback_score)
                    }, code='eb16')

                positive_feedback = float(response.reply.Item.Seller.PositiveFeedbackPercent)

                if positive_feedback <= constants.ebay_min_positive_percentage:
                    raise forms.ValidationError({
                        'ebay_ids': 'Positive feedback percentage for this item ({0}) lower or equal than {1}%.'
                        .format(ebay_id, constants.ebay_min_positive_percentage)
                    }, code='eb15')

                # item delivery time

                delivery_time = get_delivery_time(ebay_id)

                if delivery_time is None:
                    raise forms.ValidationError({'ebay_ids': 'Getting delivery time failed. Please try later.'},
                                                code='eb14')

                if delivery_time > constants.ebay_max_delivery_time:
                    raise forms.ValidationError({
                        'ebay_ids': 'Delivery time for this item ({0}) is greater than {1} days.'
                        .format(ebay_id, constants.ebay_max_delivery_time)
                    }, code='eb13')

                # getting eBay price

                self.ebay_price.append(get_ebay_price_from_response(response))

        # checking all eBay prices

        ebay_price_set = set(self.ebay_price)

        if len(ebay_price_set) == 1 and not list(ebay_price_set)[0]:
            raise forms.ValidationError({
                'ebay_ids': 'Checking eBay prices failed. All ids in request have a zero price.'
            }, code='eb17')

        if len(old_ebay_ids_to_add):
            ebay_ids += ';' + ';'.join(old_ebay_ids_to_add)

        return ebay_ids

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data['asin'] = self.clean_input_asin()
        cleaned_data['ebay_ids'] = self.clean_input_ebay_ids()

        # multiple validation
        # in update case

        if self.old_asin_not_changed and self.old_ebay_not_changed:
            raise forms.ValidationError('You have not changed anything.', code='fe1')

        profit_check = self.check_profit()

        if not self.errors and not profit_check:
            raise forms.ValidationError('Specified items do not bring the minimum desired benefit.', code='fe2')

        return cleaned_data


class SearchForm(forms.Form):
    """ Search form for pairs and orders """

    search_field = forms.CharField(max_length=constants.order_id_length, required=True)
    search_type = forms.ChoiceField(choices=((0, 'Pairs (ASIN, eBay ID, SKU or owner username)'),
                                             (1, 'Orders (Order ID)')), required=True)

    def __init__(self, is_moderator=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_moderator = is_moderator

    def clean(self):
        cleaned_data = super().clean()

        # validation based on search_type

        if int(cleaned_data['search_type']):
            if not self.is_moderator:
                raise forms.ValidationError({
                    'search_type': 'Your account type does not have the rights to search for orders.'
                }, code='sam1')

            if len(cleaned_data['search_field']) != constants.order_id_length:
                raise forms.ValidationError({
                    'search_field': 'Order ID should be {0} length.'.format(constants.order_id_length)
                }, code='sam2')

            if search('[^0-9-]', cleaned_data['search_field']):
                raise forms.ValidationError({
                    'search_field': 'Order ID should contains only numbers and hyphen (-).'
                }, code='sam3')

        return cleaned_data


class OrderProfitsForm(forms.Form):
    """ Form for entering the price for ebay and the revenue of each owner (in multi-order case) """

    ebay_price = forms.FloatField(required=True)

    def __init__(self, fields_names, amazon_price, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.amazon_price = amazon_price * constants.profit_percentage
        self.total_profit = None

        self.fields['ebay_price'].label = 'eBay price'

        for field in fields_names:
            self.fields[field] = forms.FloatField(required=True, min_value=constants.min_order_owner_profit)
            self.fields[field].label = field + '’s profit'
            self.fields[field].help_text = '''Required. Remember! You need to enter the full profit of the owner
                                            for all his items, his net profit will be calculated automatically.'''

    def clean_e_price(self):
        ebay_price = self.cleaned_data['ebay_price']

        if ebay_price <= 0:
            raise forms.ValidationError('eBay price must be greater than 0.', code='of1')

        if ebay_price >= self.amazon_price:
            raise forms.ValidationError('eBay price must be lower than {0}% of Amazon price.'
                                        .format(int(constants.profit_percentage * 100)), code='of2')

        return ebay_price

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data['ebay_price'] = self.clean_e_price()

        self.total_profit = round(self.amazon_price - cleaned_data['ebay_price'], 2)

        if sum([cleaned_data[key] for key in cleaned_data.keys() if key != 'ebay_price']) > self.total_profit:
            raise forms.ValidationError('Sum of owners profits is greater than total profit.', code='of3')

        return cleaned_data


class OrderReturnForm(forms.Form):
    """ Form for order update in return or failure case """

    return_type = forms.ChoiceField(choices=((0, 'Return'), (1, 'Refund')), required=True)
    loss = forms.FloatField(initial=0, required=True, help_text="For 'Refund' type you must specify the loss value.")

    def validate_loss(self):
        if not self.cleaned_data['return_type']:
            return

        loss = self.cleaned_data['loss']

        if loss <= 0:
            raise forms.ValidationError({'loss': 'Loss value must be greater than 0.'}, code='or1')

        return loss

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data['return_type'] = int(cleaned_data['return_type'])
        cleaned_data['loss'] = self.validate_loss()
        return cleaned_data


class OrderFilterForm(forms.Form):
    """ Form for orders filtering by created time """

    period = forms.ChoiceField(choices=((0, 'Last month'), (1, 'Two months'), (2, 'Half year'), (3, 'All time')))

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data['period'] = int(cleaned_data['period'])

        if not cleaned_data['period']:
            cleaned_data['period'] = 1
        elif cleaned_data['period'] == 1:
            cleaned_data['period'] = 2
        elif cleaned_data['period'] == 2:
            cleaned_data['period'] = 6
        else:
            cleaned_data['period'] = 0

        return cleaned_data
