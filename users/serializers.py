from rest_framework import serializers
from rest_framework.authtoken.models import Token

from config.constants import token_expiration_hours
from .models import CustomUser


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = 'username', 'pairs_count', 'profit'


class TokenSerializer(serializers.ModelSerializer):
    expires_in = serializers.IntegerField(default=token_expiration_hours)

    class Meta:
        model = Token
        fields = 'key', 'created', 'expires_in'
