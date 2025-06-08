import dataclasses

import pytest
from event.models import Event
from event.presentation.models import (
    Presentation,
    PresentationCategory,
    PresentationCategoryRelation,
    PresentationSpeaker,
    PresentationType,
)
from faker import Faker
from model_bakery import baker
from rest_framework.test import APIClient
from user.models.organization import Organization, OrganizationUserRelation
from user.models.user import UserExt


@dataclasses.dataclass
class PresentationTestEntity:
    user: UserExt
    organization: Organization
    organization_user_relation: OrganizationUserRelation
    presentation_type: PresentationType
    presentation: Presentation
    presentation_category: PresentationCategory
    presentation_category_relation: PresentationCategoryRelation
    presentation_speaker: PresentationSpeaker


@pytest.fixture
def create_user_with_organization_and_relation():
    user = baker.make(UserExt)
    organization = baker.make(Organization)
    relation = baker.make(OrganizationUserRelation, organization=organization, user=user)
    return user, organization, relation


@pytest.fixture()
def create_event(create_user_with_organization_and_relation):
    user, organization, relation = create_user_with_organization_and_relation
    event = baker.make(Event, organization=organization)
    return user, organization, relation, event


@pytest.fixture
def create_presentation_set(create_event):
    fake = Faker()
    user, organization, relation, event = create_event
    presentation_type = baker.make(PresentationType, event=event)
    presentation = baker.make(Presentation, type=presentation_type)
    presentation_category = baker.make(PresentationCategory, type=presentation_type, name=fake.name())
    presentation_category_relation = baker.make(
        PresentationCategoryRelation, presentation=presentation, category=presentation_category
    )
    presentation_speaker = baker.make(PresentationSpeaker, presentation=presentation, user=user)

    return PresentationTestEntity(
        user=user,
        organization=organization,
        organization_user_relation=relation,
        presentation_type=presentation_type,
        presentation=presentation,
        presentation_category=presentation_category,
        presentation_category_relation=presentation_category_relation,
        presentation_speaker=presentation_speaker,
    )


@pytest.fixture
def api_client():
    return APIClient()
