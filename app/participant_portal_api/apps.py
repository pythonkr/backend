from django.apps import AppConfig


class ParticipantPortalApiConfig(AppConfig):
    name = "participant_portal_api"

    def ready(self):
        from participant_portal_api.models import ModificationAudit, ModificationAuditComment
        from simple_history import register

        register(ModificationAudit, excluded_fields=["instance_type"])
        register(ModificationAuditComment)
