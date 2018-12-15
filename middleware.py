from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render_to_response


class Http400(Exception):
    """ Bad request exception """

    def __init__(self, error=None):
        self.error = error


class HttpCodesHandler(object):
    """ Middleware class for handling http error codes during views execution """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    @staticmethod
    def process_exception(request, exception):
        if isinstance(exception, Http400):
            if exception.error == 'no_ajax':
                message = 'This request should be made using AJAX.'
            else:
                message = 'Bad request.'

            return render_to_response('message.html', {'message': message, 'user': request.user})

        if isinstance(exception, Http404):
            return render_to_response('message.html', {'message': 'Page not found.', 'user': request.user})

        if isinstance(exception, PermissionDenied):
            return render_to_response('message.html', {'message': 'You are not authorised to visit this page.',
                                                       'user': request.user})
