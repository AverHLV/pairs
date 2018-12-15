from django.forms import EmailField
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser


class SignUpForm(UserCreationForm):
    email = EmailField(required=True, help_text='Required. Inform a valid email address.')

    class Meta:
        model = CustomUser
        fields = 'username', 'email', 'password1', 'password2'
