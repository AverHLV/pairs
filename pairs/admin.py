from django.contrib import admin
from django.db.models import F
from re import fullmatch
from .models import Pair, Order, CustomUser, NotAllowedSeller


def make_pairs_unchecked(_, __, queryset):
    queryset.update(checked=0)


def make_pairs_checked(_, __, queryset):
    queryset.update(checked=1)


def make_pairs_checked_false(_, __, queryset):
    queryset.update(checked=2)


def set_status_3(_, __, queryset):
    queryset.update(checked=3)


def set_status_4(_, __, queryset):
    queryset.update(checked=4)


def set_status_6(_, __, queryset):
    queryset.update(checked=6)


make_pairs_unchecked.short_description = 'Mark selected pairs as unchecked (status 0)'
make_pairs_checked.short_description = 'Mark selected pairs as checked (status 1)'
make_pairs_checked_false.short_description = 'Mark selected pairs as unsuitable (2 - Different items)'
set_status_3.short_description = 'Mark selected pairs as unsuitable (3 - Different package contain)'
set_status_4.short_description = 'Mark selected pairs as unsuitable (4 - Cannot be added to the store)'
set_status_6.short_description = 'Mark selected pairs as unsuitable (6 - Closed by owner)'


class PairInline(admin.TabularInline):
    model = Order.items.through


class MinPriceFilter(admin.SimpleListFilter):
    """ Current price equals minimum price filter """

    title = 'Current price = minimum price'
    parameter_name = 'eq_price'

    def lookups(self, request, model_admin):
        return ('yes', 'Yes'), ('no', 'No'),

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(amazon_current_price=F('amazon_minimum_price'))

        if self.value() == 'no':
            return queryset.exclude(amazon_current_price=F('amazon_minimum_price'))


@admin.register(Pair)
class PairAdmin(admin.ModelAdmin):
    readonly_fields = 'created',
    search_fields = 'asin',
    ordering = 'checked', '-created'
    list_filter = 'is_buybox_winner', MinPriceFilter

    actions = (
        make_pairs_unchecked, make_pairs_checked, make_pairs_checked_false, set_status_3, set_status_4, set_status_6
    )

    def get_search_results(self, request, queryset, search_term):
        """ Custom pair search """

        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        if fullmatch('[A-Z0-9]{2}-[A-Z0-9]{4}-[A-Z0-9]{4}', search_term) is not None:
            # search by sku

            try:
                queryset |= self.model.objects.filter(seller_sku=search_term)

            finally:
                return queryset, use_distinct

        elif fullmatch('[0-9]{12}', search_term) is not None:
            # search by eBay id

            try:
                queryset |= self.model.objects.filter(ebay_ids__contains=search_term)

            finally:
                return queryset, use_distinct

        elif fullmatch('[A-Z0-9]{10}', search_term) is None:
            # search by owner username

            try:
                queryset |= self.model.objects.filter(owner=CustomUser.objects.get(username=search_term))

            finally:
                return queryset, use_distinct

        return queryset, use_distinct


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    readonly_fields = 'created',
    search_fields = 'order_id',
    ordering = '-purchase_date',
    inlines = PairInline,
    exclude = 'items',


@admin.register(NotAllowedSeller)
class NASellerAdmin(admin.ModelAdmin):
    search_fields = 'ebay_user_id',
    ordering = 'ebay_user_id',
