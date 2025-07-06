import pytest
from django.db import reset_queries
from event.presentation.models import Presentation
from event.presentation.test.conftest import PresentationTestEntity
from pytest_django import DjangoAssertNumQueries


@pytest.mark.django_db
def test_count_queries(
    django_assert_max_num_queries: DjangoAssertNumQueries, create_presentation_set: PresentationTestEntity
):
    reset_queries()
    with django_assert_max_num_queries(5):
        queryset = Presentation.objects.get_all_nested_data()
        list(queryset)  # query evaluation
