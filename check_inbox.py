#!/usr/bin/env python3
"""Read and summarize the opensource@example.com inbox via IMAP.

Flags emails relevant to business setup and growth.
Saves a summary to inbox_summary.json for the pipeline to act on.
"""

from __future__ import annotations

import email
import email.header
import imaplib
import json
import os
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
SUMMARY_FILE = ROOT / "inbox_summary.json"

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# Business-relevant keywords to flag
PRIORITY_KEYWORDS = [
    "verify", "verification", "confirm", "welcome", "google",
    "business", "account", "activate", "setup", "security",
    "twitter", "instagram", "youtube", "x.com", "tiktok",
    "newsletter", "beehiiv", "subscriber", "payment", "stripe",
    "sponsor", "partnership", "collaboration", "opportunity",
    "free trial", "upgrade", "linkedin"
]


def decode_header_value(value: str) -> str:
    parts = email.header.decode_header(value)
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def get_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                try:
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    break
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            pass
    return body[:500]


def is_priority(subject: str, sender: str, body: str) -> bool:
    text = f"{subject} {sender} {body}".lower()
    return any(kw in text for kw in PRIORITY_KEYWORDS)


def main() -> int:
    email_user = os.getenv("SOCIAL_EMAIL", "").strip()
    email_pass = os.getenv("SOCIAL_APP_PASS", os.getenv("SOCIAL_PASS", "")).strip().replace(" ", "")

    if not email_user or not email_pass:
        print("ERROR: SOCIAL_EMAIL or SOCIAL_PASS not set in environment.")
        return 1

    print(f"Connecting to {IMAP_HOST} as {email_user}...")

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(email_user, email_pass)
    except imaplib.IMAP4.error as e:
        print(f"Login failed: {e}")
        print("Tip: Enable IMAP in Gmail Settings → See All Settings → Forwarding and POP/IMAP")
        return 1

    mail.select("inbox")
    _, message_ids = mail.search(None, "ALL")
    ids = message_ids[0].split()
    total = len(ids)
    print(f"Found {total} emails in inbox.")

    emails = []
    priority_emails = []

    for eid in reversed(ids[-30:]):  # latest 30
        _, msg_data = mail.fetch(eid, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        subject = decode_header_value(msg.get("Subject", "(no subject)"))
        sender = decode_header_value(msg.get("From", ""))
        date = msg.get("Date", "")
        body = get_body(msg)
        priority = is_priority(subject, sender, body)

        entry = {
            "id": eid.decode(),
            "subject": subject,
            "from": sender,
            "date": date,
            "priority": priority,
            "snippet": body[:200].replace("\n", " ").strip(),
        }
        emails.append(entry)
        if priority:
            priority_emails.append(entry)

    mail.logout()

    summary = {
        "checked_at": datetime.now().isoformat(),
        "total_emails": total,
        "scanned": len(emails),
        "priority_count": len(priority_emails),
        "priority_emails": priority_emails,
        "all_emails": emails,
    }

    SUMMARY_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"INBOX SUMMARY — {email_user}")
    print(f"{'='*50}")
    print(f"Total emails: {total} | Scanned: {len(emails)} | Priority: {len(priority_emails)}")

    if priority_emails:
        print(f"\n🚨 PRIORITY EMAILS ({len(priority_emails)}):")
        for e in priority_emails:
            print(f"\n  From:    {e['from'][:60]}")
            print(f"  Subject: {e['subject'][:80]}")
            print(f"  Date:    {e['date'][:40]}")
            print(f"  Snippet: {e['snippet'][:120]}")
    else:
        print("\nNo priority emails found.")

    print(f"\nFull summary saved to: {SUMMARY_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
