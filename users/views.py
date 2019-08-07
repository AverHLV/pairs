import logging
from django.contrib.auth import login
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils.encoding import force_bytes, force_text
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.template.loader import render_to_string
from django.template.context_processors import csrf
from django.core.mail import send_mail
from smtplib import SMTPException
from config import constants
from utils import secret_dict
from .tokens import account_activation_token, password_reset_token
from .models import CustomUser, Note
from .forms import SignUpForm, PasswordResetForm, NoteForm

logger = logging.getLogger('custom')


def signup(request):
    """ Create a user object and send an activation email """

    context = {'form': SignUpForm(), 'action': '/auth/signup/', 'button_text': 'Sign up'}
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

    return render(request, 'form.html', context)


def reset_password(request):
    """ Initiate password reset by entering username """

    context = {'form': PasswordResetForm(), 'action': '/auth/reset/', 'button_text': 'Submit'}
    context.update(csrf(request))

    if request.POST:
        form = PasswordResetForm(request.POST)

        if form.is_valid():
            user = form.user

            message = render_to_string('reset_email.html', {
                'user': user,
                'domain': get_current_site(request).domain,
                'uid': str(urlsafe_base64_encode(force_bytes(user.pk)))[1:].replace("'", ""),
                'token': password_reset_token.make_token(user)
            })

            try:
                send_mail('AE Pairs account password reset', message, secret_dict['em_user'], [user.email])

            except SMTPException as e:
                logger.warning('SMTP exception: {0}. For user: {1}'.format(e, user.username))

            return render(request, 'message.html', {
                'message': '''We've emailed you instructions for setting your password, 
                if an account exists with the email you entered. You should receive them shortly.'''
            })

        else:
            context['form'] = form

    return render(request, 'form.html', context)


def reset_password_confirm(request, uidb64, token):
    """ Check password reset token and redirect to change password form """

    uid = None

    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)

    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is not None and password_reset_token.check_token(user, token):
        return redirect('/auth/reset/change/{0}/'.format(uid))

    else:
        return render(request, 'message.html', {
            'message': 'The reset link was invalid, possibly because it already has been used.'
        })


def reset_password_input(request, uid):
    """ Reset password and save user model """

    try:
        user = CustomUser.objects.get(pk=uid)

    except CustomUser.DoesNotExist:
        return render(request, 'message.html', {'message': 'User ID is invalid.'})

    context = {'form': SetPasswordForm(user), 'action': '/auth/reset/change/{0}/'.format(uid),
               'button_text': 'Change password'}
    context.update(csrf(request))

    if request.POST:
        new_password = SetPasswordForm(user, request.POST)

        if new_password.is_valid():
            new_password.save()

            return render(request, 'message.html', {
                'message': 'Your password has been set. You may go ahead and sign in now.'
            })

        else:
            context['form'] = new_password

    return render(request, 'form.html', context)


def activation_sent(request):
    return render(request, 'message.html', {
        'message':
            'We sent a message to your email. Please confirm your email address to complete the registration.'
    })


def activation_success(request):
    response = render(request, 'message.html', {
        'message': 'Your account has been activated. You will be redirected to Home page after 5 seconds.'
    })
    
    response['Refresh'] = '5;URL=/'
    return response


def activate(request, uidb64, token):
    """ Check activation token and activate user account """

    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)

    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist) as e:
        logger.warning('Account activation error: {0}. For user: {1}'.format(e, request.user.username))
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.email_checked = True
        user.save()
        login(request, user)
        return redirect('/auth/activation/success/')

    else:
        return render(request, 'message.html', {
            'message': 'The confirmation link was invalid, possibly because it already has been used.'
        })


@login_required
def notes_paginator(request, page_number=1):
    """ Display notes for specific user """

    notes = Note.objects.filter(author=request.user).order_by('-created')
    notes = Paginator(notes, constants.on_page_obj_number).page(page_number)

    return render(request, 'notes.html', {
        'notes': notes,
        'page_range': constants.page_range,
        'current_page': page_number
    })


@login_required
def add_note(request):
    """ Add a new user note """

    context = {'form': NoteForm(), 'action': '/auth/notes/add_note/', 'button_text': 'Add note'}
    context.update(csrf(request))

    if request.POST:
        form = NoteForm(request.POST)

        if form.is_valid():
            new_note = form.save(commit=False)
            new_note.author = request.user
            new_note.save()

            return redirect('/auth/notes/')

        else:
            context['form'] = form

    return render(request, 'form.html', context)
