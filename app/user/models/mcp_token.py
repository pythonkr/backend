"""사용자별 MCP 토큰 — JWT 의 jti(폐기/감사) 핸들. id=jti, soft-delete(deleted_at)=폐기."""

from __future__ import annotations

from core.models import BaseAbstractModel
from core.util.dateutil import now_aware
from django.db import models

_TOUCH_THROTTLE_SECONDS = 60


class McpToken(BaseAbstractModel):
    user = models.ForeignKey("user.UserExt", on_delete=models.CASCADE, related_name="mcp_tokens")
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"MCP Token<{self.user.username}({self.id})>"

    def touch(self) -> None:
        now = now_aware()
        if self.last_used_at is None or (now - self.last_used_at).total_seconds() > _TOUCH_THROTTLE_SECONDS:
            type(self).objects.filter(pk=self.pk).update(last_used_at=now)
