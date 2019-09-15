from rest_framework.test import APITestCase, APIRequestFactory, force_authenticate
from ..models import CustomUser
from ..views_api import GetUser


class GetUserTest(APITestCase):
    """ Test GetUser api view """

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.user = CustomUser.objects.create_user('user', 'email@email.com', '1234')

    def test_getting_user(self):
        request = self.factory.get('/auth/api/users/')
        force_authenticate(request, user=self.user)
        response = GetUser.as_view()(request, username='user')
        self.assertTrue(response.status_code == 200)

    def test_getting_user_no_auth(self):
        request = self.factory.get('/auth/api/users/')
        response = GetUser.as_view()(request, username='user')
        self.assertTrue(response.status_code == 403)

    def test_getting_user_not_found(self):
        request = self.factory.get('/auth/api/users/')
        force_authenticate(request, user=self.user)
        response = GetUser.as_view()(request, username='another_user')
        self.assertTrue(response.status_code == 404)
