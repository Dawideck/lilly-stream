from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path


class AlertMailer:
    def __init__(self, gmail_address: str, gmail_app_password: str, recipient: str):
        self.gmail_address = gmail_address
        self.gmail_app_password = gmail_app_password
        self.recipient = recipient

    def send(self, subject: str, body: str, attachments: list[Path] | None = None) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.gmail_address
        message["To"] = self.recipient
        message.set_content(body)

        for attachment in attachments or []:
            message.add_attachment(
                attachment.read_bytes(),
                maintype="image",
                subtype="jpeg",
                filename=attachment.name,
            )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(self.gmail_address, self.gmail_app_password)
            smtp.send_message(message)
