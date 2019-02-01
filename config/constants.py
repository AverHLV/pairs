from unipath import Path
from math import inf

# file paths
base_dir = Path(__file__).ancestor(2)
secret_filename = base_dir.child('config').child('secret.json')
xml_header_filename = base_dir.child('templates_xml').child('header.xml')
xml_message_quantity_filename = base_dir.child('templates_xml').child('message_quantity.xml')
xml_message_product_filename = base_dir.child('templates_xml').child('message_product.xml')

# pairs models
asin_length = 10
sku_length = 12
ebay_id_length = 12
ebay_ids_max_count = 4
owner_on_delete_id = 1
order_id_length = 19

# pairs views
on_page_obj_number = 20
page_range = 5
pair_minimum = 30

failure_reasons = {
    2: 'Different items',
    3: 'Different package contain'
}

# pairs forms
amazon_max_salesrank = 500000
ebay_max_delivery_time = 9  # days
profit_percentage = 0.85
profit_buffer = 1
min_order_owner_profit = 0.5

profit_intervals = {
    (0, 10): 1.3,
    (10, 20): 1.3,
    (20, 30): 1.25,
    (30, 40): 1.2,
    (50, inf): 1.15
}

# pairs tasks
pair_days_live = 35

# users models
profit_percent = [
    {'mine': 0.4, 1: 0.15, 2: 0.2},
    {'mine': 0.7, 2: 0.3},
    {'mine': 1}
]

# utils
con_tries = 5
con_delay = 5  # seconds
ebay_trading_api_calls_number = 5000
amazon_product_api_calls_number = 18000
amazon_region = 'US'

amazon_feed_types = {
    'quantity': '_POST_INVENTORY_AVAILABILITY_DATA_',
    'product': '_POST_PRODUCT_DATA_',
    'price': '_POST_PRODUCT_PRICING_DATA_'
}

amazon_message_types = {
    'quantity': 'Inventory',
    'product': 'Product'
}

amazon_market_ids = {
    'Canada': {'id': 'A2EUQ1WTGCTBG2', 'code': 'CA'},
    'US': {'id': 'ATVPDKIKX0DER', 'code': 'US'},
    'Mexico': {'id': 'A1AM78C64UM0Y8', 'code': 'MX'},
    'Spain': {'id': 'A1RKKUPIHCS9HS', 'code': 'ES'},
    'UK': {'id': 'A1F83G8C2ARO7P', 'code': 'GB'},
    'France': {'id': 'A13V1IB3VIYZZH', 'code': 'FR'},
    'Germany': {'id': 'A1PA6795UKMFR9', 'code': 'DE'},
    'Italy': {'id': 'APJ6JRA9NG5V4', 'code': 'IT'},
    'Brazil': {'id': 'A2Q3Y263D00KWC', 'code': 'BR'},
    'India': {'id': 'A21TJRUUN4KGV', 'code': 'IN'},
    'China': {'id': 'AAHKV2X7AFYLW', 'code': 'CN'},
    'Japan': {'id': 'A1VC38T7YXB528', 'code': 'JP'},
    'Australia': {'id': 'A39IBJ37TRP1C6', 'code': 'AU'}
}
