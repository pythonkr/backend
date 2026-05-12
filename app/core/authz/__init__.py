from rest_framework import permissions, request, views
from user.models import UserExt


class IsSuperUser(permissions.BasePermission):
    message = "You do not have permission to perform this action."

    def has_permission(self, request: request.Request, view: views.APIView) -> bool:
        return isinstance(request.user, UserExt) and request.user.is_superuser
