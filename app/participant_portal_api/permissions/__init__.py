from event.presentation.models import PresentationSpeaker
from rest_framework import permissions, request, views
from user.models import UserExt


class IsSessionSpeaker(permissions.BasePermission):
    message = "You do not have permission to perform this action."

    def has_permission(self, request: request.Request, view: views.APIView) -> bool:
        if not (isinstance(request.user, UserExt) and request.user.is_active and request.user.is_authenticated):
            return False

        return (
            PresentationSpeaker.objects.filter_active()
            .filter(
                user=request.user,
                presentation__deleted_at__isnull=True,
            )
            .exists()
        )
