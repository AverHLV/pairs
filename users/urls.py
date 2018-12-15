from django.urls import path, re_path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/', auth_views.login, {'template_name': 'form.html',
                                      'extra_context': {'action': '/auth/login/', 'button_text': 'Log in'}}),
    path('logout/', auth_views.logout, {'next_page': '/'}),
    path('signup/', views.signup),
    path('stats/', views.stats),
    path('activation/sent/', views.activation_sent),
    path('activation/success/', views.activation_success),
    re_path(r'^activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$', views.activate)
]
