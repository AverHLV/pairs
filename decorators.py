import logging
from django.core.exceptions import PermissionDenied
from time import time
from middleware import Http400

logger = logging.getLogger('finder')


def moderator_required(func):
    """ Check whether the user is a moderator """

    def wrap(request, *args, **kwargs):
        if request.user.is_moderator:
            return func(request, *args, **kwargs)
        else:
            raise PermissionDenied

    wrap.__doc__ = func.__doc__
    wrap.__name__ = func.__name__
    return wrap


def is_ajax(func):
    """ Check if the request is made using ajax """

    def wrap(request, *args, **kwargs):
        if request.is_ajax():
            return func(request, *args, **kwargs)
        else:
            raise Http400('no_ajax')

    wrap.__doc__ = func.__doc__
    wrap.__name__ = func.__name__
    return wrap


def log_work_time(object_name: str):
    """ Decorator factory for logging work time of different functions """

    def decorator(function):
        def wrapper(*args, **kwargs):
            logger.info('{} starts'.format(object_name))
            start = time()
            result = function(*args, **kwargs)
            logger.info('{} work time: {:.4f} s'.format(object_name, time() - start))
            return result
        return wrapper
    return decorator
