from django.test import TestCase, RequestFactory
from users.models import CustomUser
from ..views import logs


class TestLogsView(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = CustomUser.objects.create_superuser('user', 'email@test.com', 'password')

    def test_logs(self):
        request = self.factory.get('/')
        request.user = self.user
        response = logs(request, 'default')

        self.assertEqual(response.status_code, 200)
