from django.contrib import admin
from .models import RepricerStats


@admin.register(RepricerStats)
class RepricerStatsAdmin(admin.ModelAdmin):
    model = RepricerStats
    readonly_fields = 'created',
    ordering = '-created',
    list_filter = (('created', admin.DateFieldListFilter),)
