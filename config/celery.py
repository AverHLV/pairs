from config.settings.local import BASE_NAME
from celery import Celery
from os import environ

environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

app = Celery(BASE_NAME)
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
