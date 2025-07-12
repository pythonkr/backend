from core.util.decorator import retry
from django.conf import settings
from httpx import Timeout, post

from .blocks import SlackBlocks

TimeoutTypes = None | float | tuple[float | None, float | None, float | None, float | None] | Timeout


class SlackClient:
    @retry
    def send_message(self, channel_id: str, text: str, blocks: SlackBlocks = None, timeout: TimeoutTypes = None):
        return post(
            "https://www.slack.com/api/chat.postMessage",
            headers={"Content-type": "application/json", "Authorization": f"Bearer {settings.SLACK.token}"},
            json={"channel": channel_id, "text": text, "blocks": blocks.to_dict()["blocks"]},
            timeout=timeout,
            follow_redirects=True,
        )
