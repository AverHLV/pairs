from django.urls import path, re_path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/', auth_views.login, {
        'template_name': 'login_form.html',
        'extra_context': {'action': '/auth/login/', 'button_text': 'Log in'}
    }),

    path('logout/', auth_views.logout, {'next_page': '/'}),
    path('signup/', views.signup),
    path('password_reset/', views.reset_password),
    path('password_reset/sent/', auth_views.password_reset_done, {
        'template_name': 'message.html',
        'extra_context': {
            'message': '''We've emailed you instructions for setting your password,
            if an account exists with the email you entered. You should receive them shortly.'''
        }
    }),

    re_path(r'^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
            auth_views.password_reset_confirm, name='password_reset_confirm'),

    path('reset/done/', auth_views.password_reset_complete, {
        'template': 'message.html',
        'extra_context': {
            'message': '''Your password has been set. You may go ahead and <a href="{% url 'signin' %}">sign in</a> now.
            '''
        }
    }, name='password_reset_complete'),

    path('activation/sent/', views.activation_sent),
    path('activation/success/', views.activation_success),
    re_path(r'^activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$', views.activate)
]
