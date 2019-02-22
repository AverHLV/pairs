from django.urls import include, path
from django.contrib import admin

urlpatterns = [
    path('', include('pairs.urls')),
    path('auth/', include('users.urls')),
    path('stats/', include('stats.urls')),
    path('admin/', admin.site.urls),
    path('admin/statuscheck/', include('celerybeat_status.urls')),
]
