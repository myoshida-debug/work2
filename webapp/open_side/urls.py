from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required, user_passes_test
from . import views


app_name = 'open_side'
open_login_required = login_required(login_url='open_side:login')
open_admin_required = user_passes_test(
    lambda user: user.is_staff or user.is_superuser,
    login_url='open_side:login',
)

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(
        template_name='anonymizer_app/login.html',
        extra_context={'side_name': 'OpenSide'},
        next_page='open_side:home',
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='open_side:login'), name='logout'),
    path('', open_login_required(views.menu), name='home'),
    path('menu/', open_login_required(views.menu), name='menu'),
    path('dmz/list/', open_login_required(views.dmz_list), name='dmz_list'),
    path('dmz/import/', open_login_required(views.dmz_import), name='dmz_import'),
    path('imported/<str:filename>/', open_login_required(views.imported_prompt), name='imported_prompt'),
    path('imported/<str:filename>/result/', open_login_required(views.create_result), name='create_result'),
    path('logs/', open_admin_required(views.operation_logs), name='operation_logs'),
]
