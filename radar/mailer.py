import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr


def send_email(to_addr, subject, html, text, dry_run=True, unsub_url=None):
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASS")
    sender = os.getenv("MAIL_FROM", user or "noreply@example.com")
    name = os.getenv("MAIL_FROM_NAME", "공공시장 영업 레이더")
    unsub = unsub_url or os.getenv("UNSUB_URL", "")

    html = html.replace("{unsub}", f'<a href="{unsub}">{unsub}</a>' if unsub else "고객센터로 회신")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((name, sender))
    msg["To"] = to_addr
    if unsub:
        msg["List-Unsubscribe"] = f"<{unsub}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    if dry_run or not (user and pw):
        return {"sent": False, "reason": "dry_run" if dry_run else "SMTP 자격증명 없음"}

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(msg)
    return {"sent": True}
