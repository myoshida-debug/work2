from anonflow.account_views import AccountPasswordChangeView, AccountPasswordChangeDoneView
from django.urls import path
from . import views

app_name = 'internal_ai'
urlpatterns = [
    path('password/change/', AccountPasswordChangeView.as_view(), name='password_change'),
    path('password/change/done/', AccountPasswordChangeDoneView.as_view(), name='password_change_done'),
    path('chat/images/<uuid:request_id>/<int:index>/<str:format>/', views.generated_image, name='generated_image'),
    path('chat/answers/<uuid:request_id>/<str:format>/', views.chat_download, name='chat_download'),
    path('admin/', views.admin_home, name='admin_home'),
    path('admin/ai/', views.ai_settings, name='ai_settings'),
    path('admin/ai/new/', views.ai_model_edit, name='ai_model_create'),
    path('admin/ai/<int:model_id>/', views.ai_model_edit, name='ai_model_edit'),
    path('admin/logs/', views.log_search, name='log_search'),
    path('admin/employees/', views.staff_management, name='staff_management'),
    path('admin/employees/new/', views.staff_edit, name='staff_create'),
    path('admin/employees/<int:user_id>/', views.staff_edit, name='staff_edit'),
    path('admin/staff/', views.staff_limits, name='staff_limits'),
    path('admin/staff/<int:user_id>/limits/', views.staff_limit_edit, name='staff_limit_edit'),
    path('login/', views.login_view, name='login'), path('logout/', views.logout_view, name='logout'),
    path('chat/', views.chat, name='chat'), path('api/chat/', views.chat_api, name='chat_api'),
    path('usage/', views.usage, name='usage'), path('admin/dashboard/', views.dashboard, name='dashboard'),
]
