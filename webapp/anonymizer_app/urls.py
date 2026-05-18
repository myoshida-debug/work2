from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dmz/import/', views.dmz_import, name='dmz_import'),
    path('dmz/export/', views.dmz_export, name='dmz_export'),
    path('download/prompt/<str:source_id>/', views.download_prompt, name='download_prompt'),
    path('download/restore/<str:source_id>/', views.download_restore, name='download_restore'),
]
