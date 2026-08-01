import pytest
from admin_api.serializers.event.sponsor import SponsorTagAdminSerializer
from admin_api.views.event.sponsor import SponsorTagAdminViewSet
from model_bakery import baker


@pytest.fixture
def sponsor_tag(db):
    return baker.make("sponsor.SponsorTag", color=None)


@pytest.mark.parametrize("color", ["#3498db", "#ABCDEF", None])
def test_admin_serializer_accepts_color(sponsor_tag, color):
    serializer = SponsorTagAdminSerializer(instance=sponsor_tag, data={"color": color}, partial=True)
    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("color", ["", "3498db", "#3498d", "red"])
def test_admin_serializer_rejects_invalid_color(sponsor_tag, color):
    serializer = SponsorTagAdminSerializer(instance=sponsor_tag, data={"color": color}, partial=True)
    assert not serializer.is_valid()
    assert "color" in serializer.errors


def test_admin_serializer_stores_null_color(sponsor_tag):
    serializer = SponsorTagAdminSerializer(instance=sponsor_tag, data={"color": None}, partial=True)
    assert serializer.is_valid(), serializer.errors
    tag = serializer.save()
    tag.refresh_from_db()
    assert tag.color is None


def test_json_schema_exposes_color_picker_widget():
    schema = SponsorTagAdminViewSet().get_json_schema()

    assert schema["schema"]["properties"]["color"]["type"] == ["string", "null"]
    assert "color" not in schema["schema"]["required"]
    assert schema["ui_schema"]["color"] == {"ui:widget": "color"}
