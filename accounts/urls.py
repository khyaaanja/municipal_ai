from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/',    views.login_page,      name='login'),
    path('logout/',   views.logout_view,     name='logout'),
    path('register/', views.register_page,   name='register'),
    path('profile/',  views.profile_page,    name='profile'),
    path('password/', views.change_password, name='change_password'),

    # Password reset flow (Django built-ins with custom templates)
    path('forgot-password/', auth_views.PasswordResetView.as_view(
        template_name='accounts/password_reset.html',
        email_template_name='accounts/password_reset_email.html',
        subject_template_name='accounts/password_reset_subject.txt',
        success_url='/forgot-password/sent/',
    ), name='password_reset'),
    path('forgot-password/sent/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html',
    ), name='password_reset_done'),
    path('forgot-password/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html',
        success_url='/forgot-password/complete/',
    ), name='password_reset_confirm'),
    path('forgot-password/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html',
    ), name='password_reset_complete'),
]
