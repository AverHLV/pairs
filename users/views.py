from django.contrib.auth import login
from django.contrib.sites.shortcuts import get_current_site
from django.shortcuts import redirect, render_to_response
from django.utils.encoding import force_bytes, force_text
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.template.loader import render_to_string
from django.template.context_processors import csrf
from django.core.mail import send_mail
from django.core.exceptions import ObjectDoesNotExist
from smtplib import SMTPException
from utils import secret_dict, logger
from .tokens import account_activation_token
from .models import CustomUser
from .forms import SignUpForm


def signup(request):
    """ Create a user object and send an activation email """

    context = {'form': SignUpForm(), 'user': request.user, 'action': '/auth/signup/', 'button_text': 'Sign up'}
    context.update(csrf(request))

    if request.POST:
        form = SignUpForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            message = render_to_string('activation_email.html', {
                'user': user,
                'domain': get_current_site(request).domain,
                'uid': str(urlsafe_base64_encode(force_bytes(user.pk)))[1:].replace("'", ""),
                'token': account_activation_token.make_token(user)
            })

            try:
                send_mail('Activate your AE Pairs account', message, secret_dict['em_user'], [user.email])

            except SMTPException as e:
                logger.warning('SMTP exception: {0}. For user: {1}'.format(e, user.username))

            return redirect('/auth/activation/sent/')

        else:
            context['form'] = form

    return render_to_response('form.html', context)


def activation_sent(request):
    return render_to_response('message.html', {'user': request.user,
                                               'message': '''We sent a message to your email. Please confirm your 
                                               email address to complete the registration.'''})


def activation_success(request):
    response = render_to_response('message.html', {'user': request.user,
                                                   'message': '''Your account has been activated. You will be 
                                                   redirected to Home page after 5 seconds.'''})
    response['Refresh'] = '5;URL=/'
    return response


def activate(request, uidb64, token):
    """ Check activation token and activate user account """

    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)

    except (TypeError, ValueError, OverflowError, ObjectDoesNotExist) as e:
        logger.warning('Account activation error: {0}. For user: {1}'.format(e, request.user.username))
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.email_checked = True
        user.save()
        login(request, user)
        return redirect('/auth/activation/success/')

    else:
        return render_to_response('message.html', {'user': request.user,
                                                   'message': '''The confirmation link was invalid, 
                                                   possibly because it already has been used.'''})
