from django.urls import path
from . import views

urlpatterns = [
    path('', views.graphs),
    path('users/', views.users)
]
