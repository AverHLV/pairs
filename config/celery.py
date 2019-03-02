from celery import Celery
from kombu import Queue
from os import environ
from importlib import import_module

# load settings

try:
    environ['DJANGO_SETTINGS_MODULE']

except KeyError:
    environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

settings = import_module(environ['DJANGO_SETTINGS_MODULE'])

# celery configuration

app = Celery(settings.BASE_NAME)
app.config_from_object(settings)
app.autodiscover_tasks()
app.conf.task_default_queue = 'default'

app.conf.task_queues = (
    Queue('default', routing_key='tasks'),
    Queue('workflow', routing_key='workflow'),
    Queue('repricer', routing_key='repricer')
)

task_default_exchange = 'tasks'
task_default_routing_key = 'tasks'

task_routes = {
    'pairs.tasks.amazon_update': {
        'queue': 'workflow',
        'routing_key': 'workflow',
    },

    'repricer.tasks.reprice': {
        'queue': 'repricer',
        'routing_key': 'repricer',
    }
}
