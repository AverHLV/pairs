from unipath import Path
from os import name as os_name
from math import inf

# file paths
base_dir = Path(__file__).absolute().ancestor(2)
secret_filename = base_dir.child('config').child('secret.json')
xml_header_filename = base_dir.child('templates_xml').child('header.xml')
xml_message_quantity_filename = base_dir.child('templates_xml').child('message_quantity.xml')
xml_message_product_filename = base_dir.child('templates_xml').child('message_product.xml')
xml_message_price_filename = base_dir.child('templates_xml').child('message_price.xml')
xml_message_delete_product_filename = base_dir.child('templates_xml').child('message_delete_product.xml')

# logs paths

if os_name == 'nt':
    default_log_path = base_dir.ancestor(1).child('logs').child('default_err.log')
    workflow_log_path = base_dir.ancestor(1).child('logs').child('workflow_err.log')
    repricer_log_path = base_dir.ancestor(1).child('logs').child('repricer_err.log')

else:
    default_log_path = '/home/aver/logs/celery/default_err.log'
    workflow_log_path = '/home/aver/logs/celery/workflow_err.log'
    repricer_log_path = '/home/aver/logs/celery/repricer_err.log'

load_encoding = 'utf8'

# pairs models
asin_length = 10
sku_length = 12
ebay_id_length = 12
ebay_ids_max_count = 4
reason_message_max_length = 100
owner_on_delete_id = 1
order_id_length = 19
na_seller_id_length = 50

# pairs views
on_page_obj_number = 40
page_range = 3
pair_minimum = 15

failure_reasons = {
    2: 'Different items',
    3: 'Different package contain',
    4: 'Cannot be added to the store',
    6: 'Closed by owner'
}

# pairs forms
amazon_max_salesrank = 500000
ebay_max_delivery_time = 9  # days
ebay_min_feedback_score = 1000
ebay_min_positive_percentage = 98.0
profit_percentage = 0.85
profit_buffer = 1
min_order_owner_profit = 0.5

profit_intervals = {
    (0, 20): 1.22,
    (20, 30): 1.2,
    (30, 50): 1.17,
    (50, inf): 1.12
}

amazon_approximate_price_percent = {
    (0, 10): 0.15,
    (10, 20): 0.12,
    (20, 30): 0.1,
    (30, inf): 0.07
}

# pairs tasks
pair_unsuitable_days_live = 7
amazon_workflow_delay = 180  # seconds
check_after_delay = 3600  # seconds
price_digits = 3
requests_timeout = 60

# pairs parsers

ebay_delivery_months = {
    'Jan': 1,
    'Feb': 2,
    'Mar': 3,
    'Apr': 4,
    'May': 5,
    'Jun': 6,
    'Jul': 7,
    'Aug': 8,
    'Sep': 9,
    'Oct': 10,
    'Nov': 11,
    'Dec': 12
}

# stats views

users_names_length = 5
repricer_stats_hours = 10

# users models

profit_percent = [
    {'mine': 0.3, 1: 0.3},
    {'mine': 1}
]

profit_names_special = ['Oleksandr_Yamkovyi', 'Diatlenko']
profit_percentage_special = 0.2
note_preview_length = 40

# utils
con_tries = 5
con_delay = 5  # seconds
ebay_trading_api_calls_number = 5000
amazon_product_api_calls_number = 18000
amazon_get_price_limit = 200  # requests per hour
amazon_get_price_delay = 3600
amazon_get_my_price_items_limit = 20  # max asins per request
amazon_region = 'US'

amazon_feed_types = {
    'quantity': '_POST_INVENTORY_AVAILABILITY_DATA_',
    'product': '_POST_PRODUCT_DATA_',
    'delete_product': '_POST_PRODUCT_DATA_',
    'price': '_POST_PRODUCT_PRICING_DATA_'
}

amazon_message_types = {
    'quantity': 'Inventory',
    'product': 'Product',
    'delete_product': 'Product',
    'price': 'Price'
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

# buyer tasks

us_states_abbr = {
    'AK': 'Alaska',
    'AL': 'Alabama',
    'AR': 'Arkansas',
    'AZ': 'Arizona',
    'CA': 'California',
    'CO': 'Colorado',
    'CT': 'Connecticut',
    'DE': 'Delaware',
    'FL': 'Florida',
    'GA': 'Georgia',
    'HI': 'Hawaii',
    'IA': 'Iowa',
    'ID': 'Idaho',
    'IL': 'Illinois',
    'IN': 'Indiana',
    'KS': 'Kansas',
    'KY': 'Kentucky',
    'LA': 'Louisiana',
    'MA': 'Massachusetts',
    'MD': 'Maryland',
    'ME': 'Maine',
    'MI': 'Michigan',
    'MN': 'Minnesota',
    'MO': 'Missouri',
    'MS': 'Mississippi',
    'MT': 'Montana',
    'NC': 'North Carolina',
    'ND': 'North Dakota',
    'NE': 'Nebraska',
    'NH': 'New Hampshire',
    'NJ': 'New Jersey',
    'NM': 'New Mexico',
    'NV': 'Nevada',
    'NY': 'New York',
    'OH': 'Ohio',
    'OK': 'Oklahoma',
    'OR': 'Oregon',
    'PA': 'Pennsylvania',
    'RI': 'Rhode Island',
    'SC': 'South Carolina',
    'SD': 'South Dakota',
    'TN': 'Tennessee',
    'TX': 'Texas',
    'UT': 'Utah',
    'VA': 'Virginia',
    'VT': 'Vermont',
    'WA': 'Washington',
    'WI': 'Wisconsin',
    'WV': 'West Virginia',
    'WY': 'Wyoming',
    'DC': 'District Of Columbia'
}

# repricer tasks
old_stats_days_live = 5

# logs helpers
return_last_n_lines = 300

# finder interface
timeout = 60
proxy_find_tries = 4
threshold_month_number = 3
title_n_words = 8
rank_drop_percentage = 10

stopwords = [
    'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours', 'yourself', 'yourselves', 'he',
    'him', 'his', 'himself', 'she', 'her', 'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs',
    'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are', 'was', 'were',
    'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but',
    'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between',
    'into', 'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on',
    'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all',
    'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same',
    'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now', 'pcs', 'tool', 'best',
    'premium', 'pack', 'easy', 'safe', 'superior', 'exclusive'
]

stopwords += ['set of {}'.format(i) for i in range(10)]
stopwords += ['{} pack'.format(i) for i in range(10)]
