from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required, user_passes_test
from . import views


app_name = 'close_side'
close_login_required = login_required(login_url='close_side:login')
close_admin_required = user_passes_test(
    lambda user: user.is_staff or user.is_superuser,
    login_url='close_side:login',
)

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(
        template_name='anonymizer_app/login.html',
        extra_context={'side_name': 'CloseSide'},
        next_page='close_side:menu',
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='close_side:login'), name='logout'),
    path('', close_login_required(views.menu), name='menu'),
    path('anonymize/', close_login_required(views.home), name='home'),
    path('dmz/export/', close_login_required(views.dmz_export), name='dmz_export'),
    path('dmz/results/history/', close_login_required(views.result_history_list), name='result_history_list'),
    path('dmz/results/history/<int:pk>/', close_login_required(views.result_history_preview), name='result_history_preview'),
    path('dmz/results/', close_login_required(views.result_import_list), name='result_import_list'),
    path('dmz/results/import/', close_login_required(views.result_import), name='result_import'),
    path('dmz/results/<int:pk>/delete/', close_login_required(views.result_delete), name='result_delete'),
    path('api/transcribe/', close_login_required(views.transcribe_audio), name='transcribe_audio'),
    path('api/update-payload/', close_login_required(views.update_prompt_payload), name='update_prompt_payload'),
    path('download/prompt/<str:source_id>/', close_login_required(views.download_prompt), name='download_prompt'),
    path('download/restore/<str:source_id>/', close_login_required(views.download_restore), name='download_restore'),
    path('prompts/', close_login_required(views.prompts_list), name='prompts_list'),
    path('prompts/new/', close_login_required(views.prompt_create), name='prompt_create'),
    path('prompts/<int:pk>/', close_login_required(views.prompt_preview), name='prompt_preview'),
    path('prompts/<int:pk>/edit/', close_login_required(views.prompt_edit), name='prompt_edit'),
    path('prompts/<int:pk>/delete/', close_login_required(views.prompt_delete), name='prompt_delete'),
    path('prompts/<int:pk>/send/', close_login_required(views.prompt_send_to_dmz), name='prompt_send_to_dmz'),
    path('templates/', close_login_required(views.templates_list), name='templates_list'),
    path('templates/new/', close_login_required(views.template_create), name='template_create'),
    path('templates/<int:pk>/edit/', close_login_required(views.template_edit), name='template_edit'),
    path('templates/<int:pk>/delete/', close_login_required(views.template_delete), name='template_delete'),
    path('templates/<str:template_name>/', close_login_required(views.template_detail), name='template_detail'),
    path('templates/<str:template_type>/input-defaults/', close_login_required(views.template_input_defaults_edit), name='template_input_defaults_edit'),
    path('anonymization-rules/', close_login_required(views.anonymization_rules), name='anonymization_rules'),
    path('users/', close_admin_required(views.user_list), name='user_list'),
    path('logs/', close_admin_required(views.operation_logs), name='operation_logs'),
    path('api/templates/<str:template_name>/', close_login_required(views.api_template_preview), name='api_template_preview'),
]
