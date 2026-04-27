#!/usr/bin/env python3
"""send_premium_reply.py — Auto-reply with Stripe link when someone emails "PREMIUM".

Scans inbox for emails containing "PREMIUM" in subject or body.
Sends payment link instantly. Gates on .premium_reply_{hash} per sender.
"""
from __future__ import annotations
import email, email.header, hashlib, imaplib, os, smtplib, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT      = Path(__file__).parent
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
STRIPE_LINK = "https://buy.stripe.com/your-link"

SUBJECT = "Catalyst Edge Premium — Your Payment Link"

HTML = f"""\
<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a1a;">
<h2>You're one step away from Premium access.</h2>
<p>Click the link below to subscribe at $9/month — cancel anytime:</p>
<p style="text-align:center;margin:32px 0;">
<a href="{STRIPE_LINK}" style="background:#635bff;color:#fff;padding:14px 32px;
border-radius:6px;text-decoration:none;font-weight:700;font-size:1.05em;">
Subscribe — $9/month →</a></p>
<p>After payment you'll receive confirmation within minutes and your next morning's
newsletter will include the full raw scanner CSV, dark pool signals, squeeze radar,
and priority 3:30 AM delivery.</p>
<p>Any issues — just reply to this email.<br>
Catalyst Edge Team<br>opensource@example.com</p>
</body></html>"""

PLAIN = f"""\
You're one step away from Premium access.

Subscribe here ($9/month, cancel anytime):
{STRIPE_LINK}

After payment you'll get confirmation within minutes. Your next morning's newsletter
will include the full raw scanner CSV, dark pool signals, squeeze radar, and priority
3:30 AM delivery.

Any issues — just reply.
Catalyst Edge Team
opensource@example.com
"""

def load_env() -> dict:
    env = {}
    env_file = ROOT / ".sec_email_env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env[k.strip()] = v.strip()
    for k, v in os.environ.items(): env.setdefault(k, v)
    return env

def replied_flag(email_addr: str) -> Path:
    h = hashlib.md5(email_addr.encode()).hexdigest()[:8]
    return ROOT / f".premium_reply_{h}"

def already_replied(email_addr: str) -> bool:
    return replied_flag(email_addr).exists()

def mark_replied(email_addr: str) -> None:
    replied_flag(email_addr).touch()

def decode_header_str(h: str) -> str:
    parts = email.header.decode_header(h)
    out = []
    for part, enc in parts:
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out)

def get_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                try: return part.get_payload(decode=True).decode("utf-8", errors="replace")
                except: pass
    else:
        try: return msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except: pass
    return ""

def send_reply(host, port, user, passwd, sender, to, tls) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT
    msg["From"]    = f"Catalyst Edge <{sender}>"
    msg["To"]      = to
    msg.attach(MIMEText(PLAIN, "plain"))
    msg.attach(MIMEText(HTML,  "html"))
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            if tls: s.starttls()
            s.login(user, passwd)
            s.sendmail(sender, to, msg.as_string())
        return True
    except Exception as e:
        print(f"  smtp error: {e}"); return False

def main() -> int:
    env     = load_env()
    imap_user = env.get("SMTP_USER", "")
    imap_pass = env.get("SOCIAL_APP_PASS", "").replace(" ", "")
    smtp_host = env.get("SMTP_HOST", "")
    smtp_port = int(env.get("SMTP_PORT", 587))
    smtp_pass = env.get("SMTP_PASS", "").replace(" ", "")
    sender    = env.get("EMAIL_FROM", imap_user)
    tls       = env.get("SMTP_USE_TLS", "true").lower() == "true"

    if not all([imap_user, imap_pass]):
        print("send_premium_reply: IMAP credentials not configured"); return 0

    sent = 0
    try:
        M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        M.login(imap_user, imap_pass)
        M.select("INBOX")

        # Search last 7 days for PREMIUM keyword
        _, data = M.search(None, 'SINCE "21-Mar-2026"')
        ids = data[0].split()[-50:]  # last 50 emails

        for num in ids:
            _, msg_data = M.fetch(num, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            from_addr = msg.get("From", "")
            subject   = decode_header_str(msg.get("Subject", ""))
            body      = get_body(msg)

            # Extract sender email
            import re
            m = re.search(r'[\w._%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}', from_addr)
            if not m: continue
            sender_email = m.group(0).lower()

            # Skip our own emails
            if sender_email in ("opensource@example.com", "mailer-daemon@googlemail.com"):
                continue

            # Check for PREMIUM trigger
            combined = (subject + " " + body).upper()
            if "PREMIUM" not in combined:
                continue

            if already_replied(sender_email):
                print(f"  already replied → {sender_email}")
                continue

            print(f"  PREMIUM request from {sender_email}")
            if send_reply(smtp_host, smtp_port, imap_user, smtp_pass, sender, sender_email, tls):
                mark_replied(sender_email)
                sent += 1
                print(f"    ✅ payment link sent")
            else:
                print(f"    ❌ failed")
            time.sleep(2)

        M.logout()
    except Exception as e:
        print(f"send_premium_reply: imap error: {e}")

    print(f"send_premium_reply: {sent} payment links sent")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
