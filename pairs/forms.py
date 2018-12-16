from django import forms
from re import search
from config import constants
from utils import ebay_trading_api, ebay_shopping_api, amazon_products_api, logger
from .models import Pair


class PairForm(forms.ModelForm):
    """ Creating and updating form for Pair model """

    class Meta:
        model = Pair
        fields = 'asin', 'ebay_ids'

    def __init__(self, old_data=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.amazon_price = 0
        self.ebay_price = []
        self.old_data = old_data
        self.old_asin_not_changed = False
        self.old_ebay_not_changed = False
        self.variated_item = False
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
                                <li>High end of delivery time for all items should be lower or equal than {2} days.</li>
                            </ul>
                            
                            For example: 123456789123;987654321987
                            '''.format(constants.ebay_id_length, constants.ebay_ids_max_count,
                                       constants.ebay_max_delivery_time)

    def check_profit(self):
        """ Check minimum profit for asin and all eBay ids """

        if self.amazon_price:
            for ebay_price in self.ebay_price:
                if not ebay_price:
                    continue

                price = 0

                for interval in constants.profit_intervals.keys():
                    if interval[0] <= ebay_price < interval[1]:
                        price = ebay_price * constants.profit_intervals[interval] / constants.profit_percentage
                        break

                if price + constants.profit_buffer >= self.amazon_price:
                    return False

            return True

    def clean_asin(self):
        asin = self.cleaned_data['asin']

        if self.old_data is not None:
            if asin == self.old_data['asin']:
                self.old_asin_not_changed = True
                return asin

        if len(asin) != constants.asin_length:
            raise forms.ValidationError('ASIN should be {0} length.'.format(constants.asin_length), code='am1')

        if search('[^A-Z0-9]', asin):
            raise forms.ValidationError('ASIN should contains only numbers and uppercase letters.', code='am2')

        if Pair.objects.filter(asin__exact=asin).exists():
            raise forms.ValidationError('This ASIN already exists.'.format(constants.asin_length), code='am4')

        # validation based on api response

        """
        amazon_products_api.check_calls(True, forms.ValidationError,
                                        '''Amazon api calls number is over.
                                        Please, try to add pair after {0} o’clock.
                                        '''.format(amazon_products_api.checker.start_time), code='am3')
        """

        try:
            response = amazon_products_api.api.get_matching_product_for_id(amazon_products_api.region, 'ASIN', [asin])

            """
            amazon_products_api.check_calls(True, forms.ValidationError,
                                            '''Amazon api calls number is over.
                                            Please, try to add pair after {0} o’clock.
                                            '''.format(amazon_products_api.checker.start_time), code='am3')
            """

            response_price = amazon_products_api.api.get_my_price_for_asin(amazon_products_api.region, [asin])

        except amazon_products_api.connection_error as e:
            logger.warning(e.response)
            raise forms.ValidationError('Amazon api unhandled error: {0}.'
                                        .format(e.response), code='am5')

        else:
            try:
                if response.parsed['Error']['Code']['value'] == 'InvalidParameterValue':
                    raise forms.ValidationError('Invalid ASIN.', code='am6')

                else:
                    error = response.parsed['Error']['Code']['value']
                    logger.warning(error)
                    raise forms.ValidationError('Amazon api unhandled error in response! Error: {0}.'
                                                .format(error), code='am7')

            except KeyError:
                pass

            rank = int(response.parsed['Products']['Product']['SalesRankings']['SalesRank'][0]['Rank']['value'])

            if rank > constants.amazon_max_salesrank:
                raise forms.ValidationError('Item sales rank is greater than {0}.'
                                            .format(constants.amazon_max_salesrank), code='am8')

            # checking for item variations to get price and sku

            try:
                self.amazon_price = float(response_price.parsed['Product']['Offers']['Offer']['BuyingPrice']
                                          ['ListingPrice']['Amount']['value'])

            except KeyError:
                self.variated_item = True

            else:
                self.sku = response_price.parsed['Product']['Offers']['Offer']['SellerSKU']['value']

        return asin

    def clean_ebay_ids(self):
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
            raise forms.ValidationError('eBay ids should contain only numbers and delimiter.', code='eb1')

        if ';' == ebay_ids[-1]:
            raise forms.ValidationError('Don’t put delimiter after last id.', code='eb2')

        if len(ebay_ids) > constants.ebay_id_length and search(';', ebay_ids) is None:
            raise forms.ValidationError("eBay ids delimiter should be ';'.", code='eb3')

        ebay_ids_split = ebay_ids.split(';')

        if len(ebay_ids_split) > len(set(ebay_ids_split)):
            raise forms.ValidationError('Your input string contains duplicate ids.', code='eb4')

        if len(ebay_ids_split) > constants.ebay_ids_max_count:
            raise forms.ValidationError('''Your input string contains 
                                        more than {0} ids.'''.format(constants.ebay_ids_max_count), code='eb5')

        for ebay_id in ebay_ids_split:
            if len(ebay_id) != constants.ebay_id_length:
                raise forms.ValidationError('''One of your ids has wrong length. 
                                            eBay id length should be {0}.'''.format(constants.ebay_id_length),
                                            code='eb6')

            if Pair.objects.filter(ebay_ids__contains=ebay_id).exists():
                    raise forms.ValidationError('This id ({0}) already exists.'.format(ebay_id), code='eb7')

            # validation based on api response

            """
            ebay_trading_api.check_calls(True, forms.ValidationError,
                                         '''eBay api calls number is over. Please, try to add pair tomorrow in {0}.
                                         '''.format(ebay_trading_api.checker.start_time), code='eb8')
            """

            try:
                response = ebay_trading_api.api.execute('GetItem', {'ItemID': ebay_id})
                response_status = ebay_shopping_api.api.execute('GetItemStatus', {'ItemID': ebay_id})

            except ebay_trading_api.connection_error as e:
                if e.response.dict()['Errors']['ErrorCode'] == '17':
                    raise forms.ValidationError('This id ({0}) is invalid.'.format(ebay_id), code='eb9')

                else:
                    logger.warning(e.response.dict()['Errors'])
                    raise forms.ValidationError('eBay api unhandled error: {0}.'.format(e.response.dict()['Errors']),
                                                code='eb10')

            else:
                # listing status checking

                if response_status.reply.Item.ListingStatus != 'Active':
                    raise forms.ValidationError("Listing status for this item ({0}) is not 'Active'.".format(ebay_id),
                                                code='eb11')

                # if item has service option list (multiple prices and other info)

                if type(response.reply.Item.ShippingDetails.ShippingServiceOptions) is list:
                    self.variated_item = True
                    continue

                if response.reply.Item.ReturnPolicy.ReturnsAcceptedOption == 'ReturnsNotAccepted':
                    raise forms.ValidationError('Seller does not accept return for this item ({0}).'
                                                .format(ebay_id), code='eb12')

                shipping_time = int(response.reply.Item.ShippingDetails.ShippingServiceOptions.ShippingTimeMax)
                dispatch_time = int(response.reply.Item.DispatchTimeMax)

                if shipping_time + dispatch_time > constants.ebay_max_delivery_time:
                    raise forms.ValidationError('Delivery time for this item ({0}) is greater than {1} days.'
                                                .format(ebay_id, constants.ebay_max_delivery_time), code='eb13')

                # checking for item variations to get price

                price = 0

                try:
                    response.reply.Item.Variations

                except AttributeError:
                    price = float(response.reply.Item.BuyItNowPrice.value)

                    if not price:
                        price = float(response.reply.Item.StartPrice.value)

                else:
                    self.variated_item = True

                self.ebay_price.append(price)

        if len(old_ebay_ids_to_add):
            ebay_ids += ';' + ';'.join(old_ebay_ids_to_add)

        return ebay_ids

    def clean(self):
        cleaned_data = super().clean()

        # multiple validation
        # in update case

        if self.old_asin_not_changed and self.old_ebay_not_changed:
            raise forms.ValidationError('You have not changed anything.', code='fe1')

        if not self.variated_item and not self.errors and not self.check_profit():
            raise forms.ValidationError('Specified items do not bring the minimum desired benefit.', code='fe2')

        return cleaned_data


class SearchForm(forms.Form):
    """ Search form for pairs and orders """

    search_field = forms.CharField(max_length=constants.order_id_length, required=True)
    search_type = forms.ChoiceField(choices=((0, 'Pairs (ASIN)'), (1, 'Orders (Order ID)')), required=True)

    def __init__(self, is_moderator=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_moderator = is_moderator

    def clean(self):
        cleaned_data = super().clean()

        # validation based on search_type (ASIN or Order ID)

        if not int(cleaned_data['search_type']):
            if len(cleaned_data['search_field']) != constants.asin_length:
                raise forms.ValidationError('ASIN should be {0} length.'.format(constants.asin_length), code='sam1')

            if search('[^A-Z0-9]', cleaned_data['search_field']):
                raise forms.ValidationError('ASIN should contains only numbers and uppercase letters.', code='sam2')

        else:
            if not self.is_moderator:
                raise forms.ValidationError('Your account type does not have the rights to search for orders.',
                                            code='sam3')

            if len(cleaned_data['search_field']) != constants.order_id_length:
                raise forms.ValidationError('Order ID should be {0} length.'.format(constants.order_id_length),
                                            code='sam4')

            if search('[^0-9-]', cleaned_data['search_field']):
                raise forms.ValidationError('Order ID should contains only numbers and hyphen (-).', code='sam5')

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
            raise forms.ValidationError('Loss value must be greater than 0.', code='or1')

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
