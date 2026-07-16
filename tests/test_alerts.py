from unittest.mock import MagicMock, patch

from lilly_stream.alerts import AlertMailer


@patch("lilly_stream.alerts.smtplib.SMTP_SSL")
def test_send_logs_in_and_sends_message(mock_smtp_ssl):
    smtp_instance = MagicMock()
    mock_smtp_ssl.return_value.__enter__.return_value = smtp_instance

    mailer = AlertMailer("me@gmail.com", "app-password", "recipient@example.com")
    mailer.send("Subject", "Body text")

    mock_smtp_ssl.assert_called_once_with("smtp.gmail.com", 465)
    smtp_instance.login.assert_called_once_with("me@gmail.com", "app-password")
    assert smtp_instance.send_message.call_count == 1
    sent_msg = smtp_instance.send_message.call_args[0][0]
    assert sent_msg["Subject"] == "Subject"
    assert sent_msg["To"] == "recipient@example.com"


@patch("lilly_stream.alerts.smtplib.SMTP_SSL")
def test_send_with_attachment(mock_smtp_ssl, tmp_path):
    smtp_instance = MagicMock()
    mock_smtp_ssl.return_value.__enter__.return_value = smtp_instance

    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake-jpeg-bytes")

    mailer = AlertMailer("me@gmail.com", "app-password", "recipient@example.com")
    mailer.send("Subject", "Body", attachments=[photo])

    sent_msg = smtp_instance.send_message.call_args[0][0]
    attachments = list(sent_msg.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "photo.jpg"
