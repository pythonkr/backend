from django.urls import path
from user.views import AccountHomeView, AccountLoginView, MergeConfirmView, MergeStartView, PasswordLoginView

urlpatterns = [
    path("", AccountHomeView.as_view(), name="account-home"),
    path("login/", AccountLoginView.as_view(), name="account-login"),
    path("login/password/", PasswordLoginView.as_view(), name="account-password-login"),
    path("merge/", MergeStartView.as_view(), name="account-merge-start"),
    path("merge/confirm/", MergeConfirmView.as_view(), name="account-merge-confirm"),
]
