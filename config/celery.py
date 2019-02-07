from config.settings.local import BASE_NAME
from celery import Celery
from kombu import Queue
from os import environ

environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

app = Celery(BASE_NAME)
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
app.conf.task_default_queue = 'default'

app.conf.task_queues = (
    Queue('default', routing_key='tasks'),
    Queue('workflow', routing_key='workflow'),
)

task_default_exchange = 'tasks'
task_default_routing_key = 'tasks'

task_routes = {
        'pairs.tasks.amazon_update': {
            'queue': 'workflow',
            'routing_key': 'workflow',
        },
}
