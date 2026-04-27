#!/usr/bin/env python3
"""Poll opensource@example.com for a Google verification code.
Runs for up to 3 minutes checking every 5 seconds.
"""
import imaplib, email, os, re, time

GMAIL = "opensource@example.com"
PASS  = os.getenv("SOCIAL_APP_PASS", "").replace(" ", "")

print("Polling inbox for Google verification code (3 min timeout)...")
deadline = time.time() + 180

while time.time() < deadline:
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(GMAIL, PASS)
        mail.select("inbox")
        _, ids = mail.search(None, 'FROM "google" UNSEEN')
        for eid in reversed(ids[0].split()):
            _, data = mail.fetch(eid, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            body = ""
            for part in msg.walk():
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode("utf-8", errors="replace")
            codes = re.findall(r'\b([0-9]{5,6})\b', body)
            if codes:
                print(f"\n✅ VERIFICATION CODE FOUND: {codes[0]}")
                print(f"Subject: {msg.get('Subject','')}")
                mail.logout()
                raise SystemExit(0)
        mail.logout()
    except SystemExit:
        raise
    except Exception as e:
        pass
    print(".", end="", flush=True)
    time.sleep(5)

print("\n❌ No code found within 3 minutes.")
