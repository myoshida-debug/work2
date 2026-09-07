from django.urls import path
from . import views

app_name = 'internal_ai'
urlpatterns = [
    path('login/', views.login_view, name='login'), path('logout/', views.logout_view, name='logout'),
    path('chat/', views.chat, name='chat'), path('api/chat/', views.chat_api, name='chat_api'),
    path('usage/', views.usage, name='usage'), path('admin/dashboard/', views.dashboard, name='dashboard'),
]
