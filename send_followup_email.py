#!/usr/bin/env python3
"""One-shot follow-up email sender.

Usage:
    python3 send_followup_email.py --id quantconnect_jared

Reads contacts from followup_contacts.json. Sends the email via Gmail SMTP,
then marks the contact as sent so it never fires twice.
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT         = Path(__file__).parent
CONTACTS     = ROOT / "followup_contacts.json"
ENV_FILE     = ROOT / ".sec_email_env"


def load_env() -> dict:
    env: dict = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update(os.environ)
    return env


def send(contact: dict, env: dict) -> None:
    smtp_host = env.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(env.get("SMTP_PORT", 587))
    smtp_user = env.get("SMTP_USER", env.get("EMAIL_FROM", ""))
    smtp_pass = env.get("SMTP_PASS", "")
    from_addr = env.get("EMAIL_FROM", smtp_user)

    to_addr   = contact["email"]
    subject   = contact["subject"]
    body_text = contact["body"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Catalyst Edge <{from_addr}>"
    msg["To"]      = to_addr

    msg.attach(MIMEText(body_text, "plain"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_addr, [to_addr], msg.as_string())

    print(f"  Sent follow-up to {to_addr} — {subject}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Contact ID from followup_contacts.json")
    args = parser.parse_args()

    if not CONTACTS.exists():
        print(f"ERROR: {CONTACTS} not found")
        return 1

    contacts = json.loads(CONTACTS.read_text(encoding="utf-8"))
    contact  = contacts.get(args.id)

    if not contact:
        print(f"ERROR: contact '{args.id}' not found in {CONTACTS}")
        return 1

    if contact.get("sent"):
        print(f"Already sent to {args.id} on {contact['sent']} — skipping")
        return 0

    send_date = contact.get("send_date", "")
    today     = date.today().isoformat()
    if send_date and today < send_date:
        print(f"Not yet — scheduled for {send_date}, today is {today}")
        return 0

    env = load_env()
    send(contact, env)

    contact["sent"] = today
    CONTACTS.write_text(json.dumps(contacts, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
