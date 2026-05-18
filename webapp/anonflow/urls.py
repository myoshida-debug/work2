from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', lambda request: redirect('close_side:home'), name='home'),
    path('close/', include('close_side.urls', namespace='close_side')),
    path('open/', include('open_side.urls', namespace='open_side')),
]
