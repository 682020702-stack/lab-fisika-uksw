import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urlencode

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class SMTPConfigurationError(RuntimeError):
    pass


def send_verification_email(email_to: str, nama: str, token: str) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", username)
    frontend_url = os.getenv(
        "VERIFICATION_BASE_URL", "http://127.0.0.1:8081/verify.html"
    )

    if not username or not password or not sender:
        raise SMTPConfigurationError(
            "Set SMTP_USERNAME, SMTP_PASSWORD, dan SMTP_FROM_EMAIL sebelum mengirim email."
        )

    separator = "&" if "?" in frontend_url else "?"
    verification_link = f"{frontend_url}{separator}{urlencode({'token': token})}"
    message = MIMEText(
        f"Halo {nama}, terima kasih telah mendaftar di Sistem Laboratorium Fisika. "
        f"Klik link berikut untuk verifikasi akun Anda: {verification_link}. "
        "Link ini berlaku 24 jam.",
        "plain",
        "utf-8",
    )
    message["Subject"] = "Verifikasi Akun Sistem Laboratorium Fisika"
    message["From"] = sender
    message["To"] = email_to

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)


def send_password_reset_email(email_to: str, nama: str, token: str) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", username)
    reset_url = os.getenv(
        "RESET_PASSWORD_BASE_URL",
        "http://127.0.0.1:8081/reset-password.html",
    )

    if not username or not password or not sender:
        raise SMTPConfigurationError(
            "Set SMTP_USERNAME, SMTP_PASSWORD, dan SMTP_FROM_EMAIL sebelum mengirim email."
        )

    separator = "&" if "?" in reset_url else "?"
    reset_link = f"{reset_url}{separator}{urlencode({'token': token})}"
    message = MIMEText(
        f"Halo {nama}, kami menerima permintaan untuk mereset password akun Anda. "
        f"Klik link berikut untuk membuat password baru: {reset_link}. "
        "Link ini berlaku selama 15 menit dan hanya dapat digunakan sekali. "
        "Jika Anda tidak meminta reset password, abaikan email ini.",
        "plain",
        "utf-8",
    )
    message["Subject"] = "Reset Password Sistem Laboratorium Fisika"
    message["From"] = sender
    message["To"] = email_to

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)
