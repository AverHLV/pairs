from rest_framework.authentication import TokenAuthentication, exceptions
from django.utils.timezone import get_current_timezone
from datetime import datetime, timedelta
from config import constants

current_timezone = get_current_timezone()


class ExpirationAuth(TokenAuthentication):
    """ Custom authentication with expiration token """

    def authenticate_credentials(self, key):
        model = self.get_model()

        try:
            token = model.objects.get(key=key)

        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token.')

        if self.expired(token):
            token.delete()
            raise exceptions.AuthenticationFailed('Token has expired.')

        if not token.user.is_active:
            raise exceptions.AuthenticationFailed('User inactive or deleted.')

        return token.user, token

    @staticmethod
    def expired(token) -> bool:
        return token.created < (datetime.now(current_timezone) - timedelta(hours=constants.token_expiration_hours))
