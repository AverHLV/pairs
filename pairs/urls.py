from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.pairs_paginator),
    path('page/<int:page_number>/', views.pairs_paginator),
    path('checked/<int:pair_id>/<int:result>/', views.mark_as_checked),
    path('page/<int:__>/checked/<int:pair_id>/<int:result>/', views.mark_as_checked),
    path('profits/', views.profits_table),
    path('add_pair/', views.add_pair),
    path('change_pair/<int:pair_id>/', views.change_pair),
    path('search/', views.search_for),
    path('search/<str:asin>/', views.search_from_orders),
    path('orders/', views.orders_paginator),
    path('orders/page/<int:page_number>/', views.orders_paginator),
    path('orders/profits/<int:order_id>/', views.order_profits),
    path('orders/return/<int:order_id>/', views.order_return),
    path('orders/price/<int:order_id>/<int:result>/', views.update_ebay_price),
    path('orders/page/<int:__>/price/<int:order_id>/<int:result>/', views.update_ebay_price),
    re_path(r'^orders/price/(?P<order_id>\d+)/(?P<result>\d+\.\d+)/$', views.update_ebay_price),
    re_path(r'^orders/page/(?P<_>\d+)/price/(?P<order_id>\d+)/(?P<result>\d+\.\d+)/$',
            views.update_ebay_price)
]
