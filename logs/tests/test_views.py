from django.test import TestCase, RequestFactory
from django.http import Http404
from django.contrib.auth.models import AnonymousUser
from users.models import CustomUser
from ..views import logs


class TestLogsView(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.anon_user = AnonymousUser()
        self.user = CustomUser.objects.create_superuser('user', 'email@test.com', 'password')
        self.wrong_user = CustomUser.objects.create_user('wrong_user', 'wrong_email@test.com', 'password')

    def test_logs(self):
        request = self.factory.get('/')
        request.user = self.user

        response = logs(request, 'default')
        self.assertEqual(response.status_code, 200)

        response = logs(request, 'workflow')
        self.assertEqual(response.status_code, 200)

        response = logs(request, 'repricer')
        self.assertEqual(response.status_code, 200)

    def test_logs_not_found(self):
        request = self.factory.get('/')
        request.user = self.user
        self.assertRaises(Http404, logs, request, 'log')

    def test_logs_forbidden(self):
        request = self.factory.get('/')
        request.user = self.wrong_user

        response = logs(request, 'default')
        self.assertEqual(response.status_code, 302)

    def test_logs_login(self):
        request = self.factory.get('/')
        request.user = self.anon_user

        response = logs(request, 'default')
        self.assertEqual(response.status_code, 302)
