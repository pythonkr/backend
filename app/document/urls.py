from django.urls import path
from document.views import CertificateVerifyView, DocumentDownloadView

urlpatterns = [
    path("download/<uuid:pk>/", DocumentDownloadView.as_view(), name="document-download"),
    path("verify/<str:token>/", CertificateVerifyView.as_view(), name="certificate-verify"),
]
