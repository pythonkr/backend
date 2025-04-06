import json
import logging
import logging.handlers

from django.conf import settings


class SlackHandler(logging.handlers.HTTPHandler):
    def __init__(self) -> None:
        super().__init__(host="slack.com", url="/api/chat.postMessage", method="POST", secure=True)

    def mapLogRecord(self, record: logging.LogRecord) -> dict[str, str | dict]:
        return {
            "channel": settings.SLACK.channel,
            "text": "서버 알림",
            "blocks": self.formatter.format(record),
        }

    def emit(self, record: logging.LogRecord) -> None:
        """From the logging.handlers.HTTPHandler.emit, but with some modifications to send a message to Slack."""
        try:
            connection = self.getConnection(self.host, self.secure)
            connection.request(
                method=self.method,
                url=self.url,
                body=json.dumps(self.mapLogRecord(record)).encode("utf-8"),
                headers={
                    "Content-type": "application/json",
                    "Authorization": f"Bearer {settings.SLACK.token}",
                },
            )
            connection.getresponse()
        except Exception:
            self.handleError(record)
