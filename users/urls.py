from django.urls import path, re_path, include
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(**{
        'template_name': 'login_form.html',
        'extra_context': {'action': '/auth/login/', 'button_text': 'Log in'}
    })),

    path('logout/', auth_views.LogoutView.as_view(next_page='/')),
    path('signup/', views.signup),
    path('reset/', views.reset_password),
    path('reset/change/<int:uid>/', views.reset_password_input),
    path('activation/sent/', views.activation_sent),
    path('activation/success/', views.activation_success),
    path('notes/', views.notes_paginator),
    path('notes/page/<int:page_number>/', views.notes_paginator),
    path('notes/add_note/', views.add_note),
    re_path(r'^activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$', views.activate),
    re_path(r'^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
            views.reset_password_confirm, name='password_reset_confirm'),

    # rest api urls

    path('api/', include('rest_auth.urls'))
]
