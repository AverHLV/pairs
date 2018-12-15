from django.template.loader import render_to_string
from django.core.mail import send_mail
from celery import shared_task
from celery.utils.log import get_task_logger
from smtplib import SMTPException
from datetime import datetime
from config.constants import pair_minimum
from utils import secret_dict
from .models import CustomUser

logger = get_task_logger(__name__)


@shared_task(name='Update users stats')
def update_stats():
    """ Send monthly users statistics report and update this stats for new month """

    html_message = render_to_string('stats_email.html', {
        'users': CustomUser.objects.order_by('username'),
        'pair_min': pair_minimum,
        'gen_date': datetime.now().date()
    })

    try:
        send_mail('AE Pairs monthly report', '', secret_dict['em_user'],
                  [admin['email'] for admin in secret_dict['admins']], html_message=html_message)

    except SMTPException as e:
        logger.warning('An exception occurred while sending the monthly report. SMTP exception: {0}.'.format(e))

        with open('Monthly_report_date_{0}.html'.format(datetime.now().date()), 'w') as file:
            file.write(html_message)

    for user in CustomUser.objects.all():
        user.profit = 0
        user.pairs_count = 0
        user.save(update_fields=['profit', 'pairs_count'])

    logger.info('Users statistics update completed.')
