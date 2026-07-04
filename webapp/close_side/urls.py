from functools import wraps

from django.core.exceptions import PermissionDenied
from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from . import views


app_name = 'close_side'
close_login_required = login_required(login_url='close_side:login')


def close_admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return close_login_required(_wrapped)

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
    path('dmz/results/<int:pk>/', close_login_required(views.result_detail), name='result_detail'),
    path('dmz/results/<int:pk>/rerestore/', close_login_required(views.result_rerestore), name='result_rerestore'),
    path('dmz/results/<int:pk>/delete/', close_login_required(views.result_delete), name='result_delete'),
    path('patients/', close_admin_required(views.patient_list), name='patient_list'),
    path('patients/new/', close_admin_required(views.patient_create), name='patient_create'),
    path('patients/import/', close_admin_required(views.patient_import), name='patient_import'),
    path('patients/<int:pk>/edit/', close_admin_required(views.patient_edit), name='patient_edit'),
    path('patients/<int:pk>/delete/', close_admin_required(views.patient_delete), name='patient_delete'),
    path('api/patients/<str:patient_id>/', close_login_required(views.patient_lookup), name='patient_lookup'),
    path('api/text-file-preview/', close_login_required(views.text_file_preview), name='text_file_preview'),
    path('staffs/', close_admin_required(views.staff_list), name='staff_list'),
    path('staffs/new/', close_admin_required(views.staff_create), name='staff_create'),
    path('staffs/import/', close_admin_required(views.staff_import), name='staff_import'),
    path('staffs/<int:pk>/edit/', close_admin_required(views.staff_edit), name='staff_edit'),
    path('staffs/<int:pk>/delete/', close_admin_required(views.staff_delete), name='staff_delete'),
    path('linked-persons/', close_admin_required(views.linked_person_list), name='linked_person_list'),
    path('linked-persons/new/', close_admin_required(views.linked_person_create), name='linked_person_create'),
    path('linked-persons/import/', close_admin_required(views.linked_person_import), name='linked_person_import'),
    path('linked-persons/<int:pk>/edit/', close_admin_required(views.linked_person_edit), name='linked_person_edit'),
    path('linked-persons/<int:pk>/delete/', close_admin_required(views.linked_person_delete), name='linked_person_delete'),
    path('families/', close_admin_required(views.family_list), name='family_list'),
    path('families/new/', close_admin_required(views.family_create), name='family_create'),
    path('families/import/', close_admin_required(views.family_import), name='family_import'),
    path('families/<int:pk>/edit/', close_admin_required(views.family_edit), name='family_edit'),
    path('families/<int:pk>/delete/', close_admin_required(views.family_delete), name='family_delete'),
    path('guardians/', close_admin_required(views.guardian_list), name='guardian_list'),
    path('guardians/new/', close_admin_required(views.guardian_create), name='guardian_create'),
    path('guardians/import/', close_admin_required(views.guardian_import), name='guardian_import'),
    path('guardians/<int:pk>/edit/', close_admin_required(views.guardian_edit), name='guardian_edit'),
    path('guardians/<int:pk>/delete/', close_admin_required(views.guardian_delete), name='guardian_delete'),
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
    path('templates/new/', close_admin_required(views.template_create), name='template_create'),
    path('templates/<int:pk>/edit/', close_admin_required(views.template_edit), name='template_edit'),
    path('templates/<int:pk>/toggle-active/', close_admin_required(views.template_toggle_active), name='template_toggle_active'),
    path('templates/<int:pk>/delete/', close_admin_required(views.template_delete), name='template_delete'),
    path('templates/reorder/', close_admin_required(views.template_reorder), name='template_reorder'),
    path('templates/<str:template_type>/fields/', close_admin_required(views.template_input_fields_edit), name='template_input_fields_edit'),
    path('templates/<str:template_type>/checkbox-options/', close_admin_required(views.template_checkbox_options_edit), name='template_checkbox_options_edit'),
    path('templates/<str:template_name>/', close_login_required(views.template_detail), name='template_detail'),
    path('templates/<str:template_type>/input-defaults/', close_admin_required(views.template_input_defaults_edit), name='template_input_defaults_edit'),
    path('anonymization-rules/', close_login_required(views.anonymization_rules), name='anonymization_rules'),
    path('users/', close_admin_required(views.user_list), name='user_list'),
    path('logs/', close_admin_required(views.operation_logs), name='operation_logs'),
    path('api/templates/<str:template_name>/', close_login_required(views.api_template_preview), name='api_template_preview'),
]
