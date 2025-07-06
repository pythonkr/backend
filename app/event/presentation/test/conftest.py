import dataclasses
from datetime import datetime, timedelta

import pytest
from event.models import Event
from event.presentation.models import (
    CallForPresentationSchedule,
    Presentation,
    PresentationCategory,
    PresentationCategoryRelation,
    PresentationSpeaker,
    PresentationType,
    Room,
    RoomSchedule,
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
    room: Room
    room_schedule: RoomSchedule
    call_for_presentation_schedule: CallForPresentationSchedule


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

    # 기존 데이터 생성
    presentation_type = baker.make(PresentationType, event=event)
    presentation = baker.make(Presentation, type=presentation_type)
    presentation_category = baker.make(PresentationCategory, type=presentation_type, name=fake.name())
    presentation_category_relation = baker.make(
        PresentationCategoryRelation, presentation=presentation, category=presentation_category
    )
    presentation_speaker = baker.make(PresentationSpeaker, presentation=presentation, user=user)

    # Room과 RoomSchedule 데이터 생성
    room = baker.make(Room, event=event, name=fake.company())
    start_time = datetime.now()
    room_schedule = baker.make(
        RoomSchedule, room=room, presentation=presentation, start_at=start_time, end_at=start_time + timedelta(hours=1)
    )

    # CallForPresentationSchedule 데이터 생성
    cfp_start = start_time - timedelta(days=30)
    call_for_presentation_schedule = baker.make(
        CallForPresentationSchedule,
        presentation_type=presentation_type,
        start_at=cfp_start,
        end_at=cfp_start + timedelta(days=14),
    )

    return PresentationTestEntity(
        user=user,
        organization=organization,
        organization_user_relation=relation,
        presentation_type=presentation_type,
        presentation=presentation,
        presentation_category=presentation_category,
        presentation_category_relation=presentation_category_relation,
        presentation_speaker=presentation_speaker,
        room=room,
        room_schedule=room_schedule,
        call_for_presentation_schedule=call_for_presentation_schedule,
    )


@pytest.fixture
def api_client():
    return APIClient()
