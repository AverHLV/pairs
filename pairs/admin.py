from django.contrib import admin
from .models import Pair, Order


def make_pairs_unchecked(_, __, queryset):
    queryset.update(checked=0)


def make_pairs_checked(_, __, queryset):
    queryset.update(checked=1)


def make_pairs_checked_false(_, __, queryset):
    queryset.update(checked=2)


make_pairs_unchecked.short_description = 'Mark selected pairs as unchecked (status 0)'
make_pairs_checked.short_description = 'Mark selected pairs as checked (status 1)'
make_pairs_checked_false.short_description = 'Mark selected pairs as checked (status 2)'


class PairInline(admin.TabularInline):
    model = Order.items.through


@admin.register(Pair)
class PairAdmin(admin.ModelAdmin):
    readonly_fields = 'created',
    search_fields = 'asin',
    ordering = 'checked', '-created'
    actions = make_pairs_unchecked, make_pairs_checked, make_pairs_checked_false


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    readonly_fields = 'created',
    search_fields = 'order_id',
    ordering = '-purchase_date',
    inlines = PairInline,
    exclude = 'items',
