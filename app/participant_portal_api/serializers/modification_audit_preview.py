from participant_portal_api.models import ModificationAudit
from participant_portal_api.serializers.modification_audit import ModificationAuditResponsePortalSerializer
from participant_portal_api.serializers.presentation import PresentationPortalSerializer
from participant_portal_api.serializers.user import UserPortalSerializer
from rest_framework import serializers


class ModificationAuditPresentationPreviewPortalSerializer(serializers.ModelSerializer):
    modification_audit = ModificationAuditResponsePortalSerializer(read_only=True, source="*")
    original = PresentationPortalSerializer(read_only=True, source="fake_original_instance")
    modified = PresentationPortalSerializer(read_only=True, source="fake_modified_instance")

    class Meta:
        model = ModificationAudit
        fields = read_only_fields = ("id", "modification_audit", "original", "modified")


class ModificationAuditUserPreviewPortalSerializer(serializers.ModelSerializer):
    modification_audit = ModificationAuditResponsePortalSerializer(read_only=True, source="*")
    original = UserPortalSerializer(read_only=True, source="fake_original_instance")
    modified = UserPortalSerializer(read_only=True, source="fake_modified_instance")

    class Meta:
        model = ModificationAudit
        fields = read_only_fields = ("id", "modification_audit", "original", "modified")
