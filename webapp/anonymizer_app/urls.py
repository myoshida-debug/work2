from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dmz/import/', views.dmz_import, name='dmz_import'),
    path('dmz/export/', views.dmz_export, name='dmz_export'),
    path('dmz/list/', views.dmz_list, name='dmz_list'),
    path('download/prompt/<str:source_id>/', views.download_prompt, name='download_prompt'),
    path('download/restore/<str:source_id>/', views.download_restore, name='download_restore'),
    path('prompts/', views.prompts_list, name='prompts_list'),
    path('prompts/new/', views.prompt_create, name='prompt_create'),
    path('prompts/<int:pk>/edit/', views.prompt_edit, name='prompt_edit'),
    path('templates/', views.templates_list, name='templates_list'),
    path('templates/new/', views.template_create, name='template_create'),
    path('templates/<int:pk>/edit/', views.template_edit, name='template_edit'),
    path('templates/<str:template_name>/', views.template_detail, name='template_detail'),
    path('anonymization-rules/', views.anonymization_rules, name='anonymization_rules'),
    path('api/templates/<str:template_name>/', views.api_template_preview, name='api_template_preview'),
]
