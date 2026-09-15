from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/',              views.login_page,         name='login'),
    path('logout/',             views.logout_view,        name='logout'),
    path('register/',           views.register_page,      name='register'),
    path('tourist-pass/',       views.tourist_pass,       name='tourist_pass'),
    path('tourist-pass/clear/', views.clear_tourist_pass, name='tourist_pass_clear'),
    path('profile/',       views.profile_page,       name='profile'),
    path('password/',      views.change_password,    name='change_password'),
    path('notifications/', views.notifications_page, name='notifications'),

    # Email verification
    path('verify-email/<uuid:token>/', views.verify_email,       name='verify_email'),
    path('resend-verification/',       views.resend_verification, name='resend_verification'),

    # Two-Factor Authentication (TOTP)
    path('2fa/setup/',    views.totp_setup,    name='totp_setup'),
    path('2fa/verify/',   views.totp_verify,   name='totp_verify'),
    path('2fa/disable/',  views.totp_disable,  name='totp_disable'),

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
