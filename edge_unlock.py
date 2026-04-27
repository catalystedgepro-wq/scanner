"""edge_unlock.py — Magic-link + HMAC cookie auth for Edge Pro consumers.

Separate layer from api_auth.py (X-API-Key for developers):
- Developers: get a raw key, paste as X-API-Key header. api_auth.py handles.
- Consumers: enter email on /scanner/ → magic link emailed → cookie set.

Premium allowlist is driven by PREMIUM_EMAIL_TO in .sec_email_env. Swap for a
Stripe webhook later — just update _is_premium().

Token format (both magic link and cookie):
    base64url(email) "." base64url(exp_ts_int) "." base64url(hmac_sha256)

Cookie name: edge_tier. 90-day TTL. HttpOnly, Secure, SameSite=Lax.
Magic-link token: 24-hour TTL, single-shot consumption not enforced (idempotent).
"""
from __future__ import annotations

import base64
import email.utils
import hashlib
import hmac
import os
import secrets
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".sec_email_env"
AUDIT_LOG = ROOT / "edge_unlock_audit.log"

COOKIE_NAME = "edge_tier"
COOKIE_TTL_SECONDS = 90 * 24 * 3600
MAGIC_LINK_TTL_SECONDS = 24 * 3600
SHORT_UNLOCK_TTL_SECONDS = 15 * 60  # fallback token in URL for one session

_PUBLIC_BASE_URL_DEFAULT = "https://catalystedgescanner.com"


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def _write_env_kv(key: str, value: str) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    found = False
    out: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _get_secret() -> bytes:
    env = _load_env()
    secret = env.get("EDGE_UNLOCK_SECRET") or os.environ.get("EDGE_UNLOCK_SECRET", "")
    if not secret:
        secret = secrets.token_hex(32)
        try:
            _write_env_kv("EDGE_UNLOCK_SECRET", secret)
        except Exception:
            pass
    return secret.encode("utf-8")


def _premium_emails() -> set[str]:
    env = _load_env()
    raw = env.get("PREMIUM_EMAIL_TO", "") or os.environ.get("PREMIUM_EMAIL_TO", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _admin_emails() -> set[str]:
    env = _load_env()
    raw = env.get("ADMIN_EMAILS", "") or os.environ.get("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_admin(email: str) -> bool:
    if not email:
        return False
    return email.strip().lower() in _admin_emails()


def is_premium(email: str) -> bool:
    """True if the email is allowed to RECEIVE a magic link.

    Admins always qualify.
    Active paid subscribers (subscriber_store) always qualify.
    Legacy PREMIUM_EMAIL_TO allowlist still honored for founder/comp accounts.
    """
    if not email:
        return False
    e = email.strip().lower()
    if e in _admin_emails():
        return True
    try:
        from subscriber_store import is_active_subscriber
        if is_active_subscriber(e):
            return True
    except Exception:
        pass
    return e in _premium_emails()


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def issue_token(email: str, ttl_seconds: int) -> str:
    """Produce an HMAC-signed token: b64u(email).b64u(exp).b64u(sig)."""
    email = email.strip().lower()
    exp = int(time.time()) + int(ttl_seconds)
    msg = f"{email}|{exp}".encode("utf-8")
    sig = hmac.new(_get_secret(), msg, hashlib.sha256).digest()
    return f"{_b64u(email.encode())}.{_b64u(str(exp).encode())}.{_b64u(sig)}"


def verify_token(token: str) -> dict:
    """Return {valid, expired, email}. Never raises."""
    result = {"valid": False, "expired": False, "email": None}
    if not token or token.count(".") != 2:
        return result
    try:
        e_b64, x_b64, s_b64 = token.split(".")
        email = _b64u_decode(e_b64).decode("utf-8")
        exp = int(_b64u_decode(x_b64).decode("utf-8"))
        sig = _b64u_decode(s_b64)
    except Exception:
        return result
    expected = hmac.new(
        _get_secret(), f"{email}|{exp}".encode("utf-8"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(sig, expected):
        return result
    result["email"] = email
    if int(time.time()) > exp:
        result["expired"] = True
        return result
    result["valid"] = True
    return result


def tier_for_cookie(cookie_value: str) -> dict:
    """Return live tier based on cookie identity + current subscription status.

    Cookie = identity proof (signed email). Never trusted alone as a license.
    License = subscriber_store lookup on EVERY call. That's how cancellations
    and failed payments auto-lock the scanner without any expiry job.

    Lookup order:
      1. Cookie signature invalid → free.
      2. Email in ADMIN_EMAILS env → admin (never re-checked, never expires).
      3. subscriber_store.active == True → tier from record (pro/reader).
      4. Legacy PREMIUM_EMAIL_TO allowlist → pro (founder/comp grandfathering).
      5. Otherwise → free (cookie is a stale identity, subscription lapsed).
    """
    info = verify_token(cookie_value) if cookie_value else {"valid": False}
    if not info.get("valid"):
        return {"tier": "free", "email": None, "status": "no_cookie"}
    email = (info.get("email") or "").strip().lower()
    if is_admin(email):
        return {"tier": "admin", "email": email, "status": "admin"}
    try:
        from subscriber_store import subscription_status
        sub = subscription_status(email)
        if sub.get("active"):
            tier = sub.get("tier") or "pro"
            return {
                "tier": tier if tier in {"pro", "reader"} else "pro",
                "email": email,
                "status": sub.get("status", "active"),
                "period_end": sub.get("period_end"),
            }
        if sub.get("status") and sub.get("status") != "none":
            return {"tier": "free", "email": email, "status": sub.get("status")}
    except Exception:
        pass
    if email in _premium_emails():
        return {"tier": "pro", "email": email, "status": "legacy_allowlist"}
    return {"tier": "free", "email": email, "status": "no_subscription"}


def _public_base_url() -> str:
    env = _load_env()
    return (
        env.get("EDGE_PUBLIC_BASE_URL")
        or os.environ.get("EDGE_PUBLIC_BASE_URL")
        or _PUBLIC_BASE_URL_DEFAULT
    ).rstrip("/")


def build_magic_link(email: str) -> str:
    token = issue_token(email, MAGIC_LINK_TTL_SECONDS)
    return f"{_public_base_url()}/api/unlock/claim?t={token}"


def _audit(action: str, email: str, extra: str = "") -> None:
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\t"
                f"{action}\t{email}\t{extra}\n"
            )
    except Exception:
        pass


def send_magic_link_email(email: str) -> dict:
    """Send the magic link via SMTP. Returns {ok, error}."""
    env = _load_env()
    host = env.get("SMTP_HOST", "")
    port = env.get("SMTP_PORT", "587")
    user = env.get("SMTP_USER", "")
    password = env.get("SMTP_PASS", "").replace(" ", "")
    mail_from = env.get("EMAIL_FROM", user) or user
    use_tls = env.get("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}

    if not all([host, port, user, password]):
        _audit("send_error", email, "smtp_not_configured")
        return {"ok": False, "error": "smtp_not_configured"}

    link = build_magic_link(email)

    subject = "Unlock Edge Pro on this device"
    text_body = (
        f"Click the link below to unlock Edge Pro on this device.\n\n"
        f"{link}\n\n"
        f"The link expires in 24 hours. If you didn't request this, ignore this email.\n\n"
        f"— Catalyst Edge"
    )
    html_body = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;
  background:#0d1117;color:#c9d1d9;padding:24px">
  <div style="max-width:480px;margin:0 auto;background:#161b22;border:1px solid #30363d;
    border-radius:12px;padding:28px">
    <div style="color:#d4a843;font-weight:800;font-size:18px;margin-bottom:14px">
      ⚡ Catalyst Edge
    </div>
    <h2 style="color:#fff;font-size:20px;margin:0 0 14px">Unlock Edge Pro</h2>
    <p style="line-height:1.55;color:#c9d1d9">
      Click the button below to unlock the full Edge Pro catalyst surface on this device.
      The link works for 24 hours and stays active for 90 days after you click it.
    </p>
    <p style="margin:24px 0">
      <a href="{link}" style="display:inline-block;background:#2ea043;color:#0d1117;
        padding:12px 22px;border-radius:8px;font-weight:700;text-decoration:none">
        Unlock Edge Pro →
      </a>
    </p>
    <p style="font-size:13px;color:#8b949e;line-height:1.5">
      If the button doesn't work, paste this URL into your browser:<br>
      <span style="color:#58a6ff;word-break:break-all">{link}</span>
    </p>
    <p style="font-size:12px;color:#6e7681;margin-top:24px;border-top:1px solid #30363d;
      padding-top:14px">
      Didn't request this? You can safely ignore the email — no account is created until
      you click the link.
    </p>
  </div>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["From"] = (
        f"Catalyst Edge <{mail_from}>"
        if "<" not in mail_from
        else mail_from
    )
    msg["To"] = email
    msg["Subject"] = subject
    msg["Date"] = email_utils_formatdate()
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        server = smtplib.SMTP(host, int(port), timeout=30)
        if use_tls:
            server.starttls()
        server.login(user, password)
        server.sendmail(mail_from, [email], msg.as_string())
        server.quit()
        _audit("sent", email, "ok")
        return {"ok": True}
    except Exception as exc:
        _audit("send_error", email, type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}


def email_utils_formatdate() -> str:
    return email.utils.formatdate(localtime=True)
