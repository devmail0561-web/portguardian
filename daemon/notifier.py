"""Système de notifications multi-canal."""

import asyncio
import json
import logging
import smtplib
import urllib.request
import urllib.error
from email.mime.text import MIMEText

from daemon.config import DaemonConfig

logger = logging.getLogger("portguardian.notifier")


class Notifier:
    """Envoie des notifications via webhook, Slack, ou email."""

    def __init__(self, config: DaemonConfig) -> None:
        self.config = config

    async def send(self, event: dict) -> None:
        """Dispatche la notification vers tous les canaux configurés."""
        tasks = []

        if self.config.webhook_url:
            tasks.append(self._send_webhook(event))
        if self.config.slack_webhook_url:
            tasks.append(self._send_slack(event))
        if self.config.email_to:
            tasks.append(self._send_email(event))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_webhook(self, event: dict) -> None:
        """Envoie un POST JSON vers un webhook générique."""
        payload = json.dumps(event).encode("utf-8")
        req = urllib.request.Request(
            self.config.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            await asyncio.to_thread(urllib.request.urlopen, req, timeout=10)
            logger.debug("Webhook envoyé: %s", event["type"])
        except urllib.error.URLError as e:
            logger.error("Échec webhook: %s", e)

    async def _send_slack(self, event: dict) -> None:
        """Envoie une notification Slack via incoming webhook."""
        severity_emoji = {
            "critical": ":rotating_light:",
            "warning": ":warning:",
            "info": ":information_source:",
        }
        emoji = severity_emoji.get(event.get("severity", "info"), ":bell:")

        payload = json.dumps({
            "text": f"{emoji} *PortGuardian* — {event['message']}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *PortGuardian*\n{event['message']}",
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Type: `{event['type']}`"},
                        {"type": "mrkdwn", "text": f"Sévérité: `{event.get('severity', 'info')}`"},
                    ],
                },
            ],
        }).encode("utf-8")

        req = urllib.request.Request(
            self.config.slack_webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            await asyncio.to_thread(urllib.request.urlopen, req, timeout=10)
            logger.debug("Slack envoyé: %s", event["type"])
        except urllib.error.URLError as e:
            logger.error("Échec Slack: %s", e)

    async def _send_email(self, event: dict) -> None:
        """Envoie un email d'alerte."""
        subject = f"[PortGuardian] {event['type']}: {event['message'][:80]}"
        body = (
            f"Événement: {event['type']}\n"
            f"Sévérité: {event.get('severity', 'info')}\n"
            f"Message: {event['message']}\n"
        )
        details = event.get("details")
        if details:
            body += f"\nDétails:\n{json.dumps(details, indent=2)}\n"

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.config.email_from
        msg["To"] = self.config.email_to

        try:
            await asyncio.to_thread(self._smtp_send, msg)
            logger.debug("Email envoyé à %s", self.config.email_to)
        except Exception as e:
            logger.error("Échec email: %s", e)

    def _smtp_send(self, msg: MIMEText) -> None:
        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
            if self.config.smtp_user:
                server.starttls()
                server.login(self.config.smtp_user, self.config.smtp_pass)
            server.send_message(msg)
