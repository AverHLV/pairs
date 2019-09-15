from rest_framework import generics, permissions
from .models import CustomUser
from .serializers import UserSerializer


class GetUser(generics.RetrieveAPIView):
    """ Get user info view """

    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = permissions.IsAuthenticated,
    lookup_field = 'username'
