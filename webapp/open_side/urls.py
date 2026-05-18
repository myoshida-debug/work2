from django.urls import path
from . import views


app_name = 'open_side'

urlpatterns = [
    path('', views.dmz_list, name='home'),
    path('dmz/list/', views.dmz_list, name='dmz_list'),
    path('dmz/import/', views.dmz_import, name='dmz_import'),
    path('imported/<str:filename>/', views.imported_prompt, name='imported_prompt'),
]
