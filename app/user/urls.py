from django.urls import path
from user.account_views.account import account_home, account_login, account_logout, password_login
from user.account_views.email import (
    add_email,
    confirm_email,
    delete_email,
    manage_emails,
    resend_email,
    set_primary_email,
)
from user.account_views.merge import merge_confirm, merge_password, merge_start
from user.account_views.password import password_change, password_reset, password_reset_from_key

urlpatterns = [
    path("", account_home, name="account-home"),
    path("login/", account_login, name="account-login"),
    path("login/password/", password_login, name="account-password-login"),
    path("logout/", account_logout, name="account-logout"),
    path("password/", password_change, name="account-password-change"),
    path("password/reset/", password_reset, name="account-password-reset"),
    path("password/reset/key/<str:key>/", password_reset_from_key, name="account-password-reset-from-key"),
    path("merge/", merge_start, name="account-merge-start"),
    path("merge/password/", merge_password, name="account-merge-password"),
    path("merge/confirm/", merge_confirm, name="account-merge-confirm"),
    path("email/", manage_emails, name="account-email"),
    path("email/add/", add_email, name="account-email-add"),
    path("email/delete/", delete_email, name="account-email-delete"),
    path("email/resend/", resend_email, name="account-email-resend"),
    path("email/primary/", set_primary_email, name="account-email-primary"),
    path("email/confirm/<str:key>/", confirm_email, name="account-email-confirm"),
]
