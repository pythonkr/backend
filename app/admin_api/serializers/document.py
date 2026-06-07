from core.const.serializer import COMMON_ADMIN_FIELDS
from core.serializer.base_abstract_serializer import BaseAbstractSerializer
from core.serializer.json_schema_serializer import JsonSchemaSerializer
from core.serializer.read_only_serializer import ReadOnlyModelSerializer
from document.models import DocumentTemplate, IssuedDocument
from rest_framework import serializers


class DocumentTemplateAdminSerializer(BaseAbstractSerializer, JsonSchemaSerializer, serializers.ModelSerializer):
    class Meta:
        model = DocumentTemplate
        fields = COMMON_ADMIN_FIELDS + ("document_type", "body")

    def validate(self, attrs: dict) -> dict:
        if self.instance is not None and IssuedDocument.objects.filter(template=self.instance).exists():
            raise serializers.ValidationError("이미 발급에 사용된 템플릿은 수정할 수 없습니다. 새 템플릿을 만드세요.")

        document_type = attrs.get("document_type", getattr(self.instance, "document_type", None))
        conflicting = DocumentTemplate.objects.filter_active().filter(document_type=document_type)
        if self.instance is not None:
            conflicting = conflicting.exclude(pk=self.instance.pk)
        if conflicting.exists():
            raise serializers.ValidationError(
                {"document_type": "이미 활성화된 동일 타입 템플릿이 있습니다. 기존 템플릿을 먼저 삭제하세요."}
            )
        return attrs


class IssuedDocumentAdminSerializer(
    BaseAbstractSerializer, JsonSchemaSerializer, ReadOnlyModelSerializer, serializers.ModelSerializer
):
    class _TemplateSerializer(serializers.ModelSerializer):
        class Meta:
            model = DocumentTemplate
            read_only_fields = fields = ("id", "document_type")

    class _IssuableSerializer(serializers.Serializer):
        app_label = serializers.CharField(source="_meta.app_label", read_only=True)
        db_table = serializers.CharField(source="_meta.db_table", read_only=True)
        id = serializers.CharField(source="pk", read_only=True)
        label = serializers.StringRelatedField(source="*")

    template = _TemplateSerializer()
    document_number = serializers.CharField(read_only=True)
    issuable = _IssuableSerializer(read_only=True)
    revoked_by = serializers.StringRelatedField()

    class Meta:
        model = IssuedDocument
        fields = COMMON_ADMIN_FIELDS + (
            "document_number",
            "issuable",
            "template",
            "context",
            "revoked_at",
            "revoked_by",
        )
