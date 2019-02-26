from django.urls import path
from . import views

urlpatterns = [
    path('<str:log_type>/', views.logs)
]
