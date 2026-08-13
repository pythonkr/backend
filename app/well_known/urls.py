from django.urls import path
from well_known.views import retrieve_rosa_discovery

urlpatterns = [
    path("rosa", retrieve_rosa_discovery, name="rosa"),
]
