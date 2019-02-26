from django.shortcuts import render
from django.http import Http404
from django.contrib.auth.decorators import login_required, user_passes_test
from config import constants
from .helpers import tail, process_log_strings


@login_required
@user_passes_test(lambda u: u.is_superuser and u.is_staff and u.is_active)
def logs(request, log_type):
    """ Get and display specified log tail """

    if log_type == 'default':
        log = tail(constants.default_log_path)
    elif log_type == 'workflow':
        log = tail(constants.workflow_log_path)
    else:
        raise Http404

    return render(request, 'logs_page.html', {'log': process_log_strings(log)})
