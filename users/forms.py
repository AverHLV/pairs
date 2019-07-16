from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, Note


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text='Required. Inform a valid email address.')

    class Meta:
        model = CustomUser
        fields = 'username', 'email', 'password1', 'password2'


class PasswordResetForm(forms.Form):
    username = forms.CharField(max_length=191)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None

    def clean_username(self):
        try:
            self.user = CustomUser.objects.get(username=self.cleaned_data['username'])

        except CustomUser.DoesNotExist:
            raise forms.ValidationError('This user does not exist')


class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = 'text',
