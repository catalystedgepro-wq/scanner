#!/usr/bin/env python3
"""Send SEC catalyst outputs via SMTP.

Required env vars:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO
Optional:
  EMAIL_FROM, SMTP_USE_TLS
"""

from __future__ import annotations

import datetime as dt
import json
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path


def fetch_beehiiv_subscribers(api_key: str, pub_id: str) -> list[str]:
    """Fetch all active subscriber emails from Beehiiv API v2."""
    emails: list[str] = []
    cursor: str | None = None
    api_base = "https://api.beehiiv.com/v2"

    while True:
        url = f"{api_base}/publications/{pub_id}/subscriptions?limit=100&status=active"
        if cursor:
            url += f"&page={cursor}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"WARNING: Beehiiv subscriber fetch failed {e.code}: {e.read().decode()}")
            break

        for sub in body.get("data", []):
            email = (sub.get("email") or "").strip()
            if email:
                emails.append(email)

        if body.get("has_more") and body.get("next_cursor"):
            cursor = body["next_cursor"]
        else:
            break

    return emails


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    smtp_host = require_env("SMTP_HOST")
    smtp_port = int(require_env("SMTP_PORT"))
    smtp_user = require_env("SMTP_USER")
    smtp_pass = require_env("SMTP_PASS").replace(" ", "")
    email_to = os.getenv("EMAIL_TO", "").strip()
    email_from_raw = os.getenv("EMAIL_FROM", smtp_user).strip()
    # Format as "Catalyst Edge <email>" for professional display name
    email_from = f"Catalyst Edge <{email_from_raw}>" if "<" not in email_from_raw else email_from_raw
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}
    newsletter_mode = os.getenv("NEWSLETTER_MODE", "0").strip().lower() in {"1", "true", "yes"}

    root = Path(__file__).parent
    tickers_file = root / "sec_catalyst_tickers.txt"
    csv_file = root / "sec_catalyst_latest.csv"
    momentum_file = root / "sec_catalyst_priority_momentum.txt"
    quality_file = root / "sec_catalyst_priority_quality.txt"
    momentum_csv = root / "sec_catalyst_ranked_momentum.csv"
    quality_csv = root / "sec_catalyst_ranked_quality.csv"
    gappers_file = root / "sec_top_gappers_tickers.txt"
    value_file = root / "sec_top_value_tickers.txt"
    moat_file = root / "sec_top_moat_tickers.txt"
    moat_core_file = root / "sec_top_moat_core_tickers.txt"
    moat_emerging_file = root / "sec_top_moat_emerging_tickers.txt"
    clean_gappers_file = root / "sec_clean_gappers_tickers.txt"
    clean_value_file = root / "sec_clean_value_tickers.txt"
    clean_moat_core_file = root / "sec_clean_moat_core_tickers.txt"
    gappers_csv = root / "sec_top_gappers.csv"
    value_csv = root / "sec_top_value.csv"
    moat_csv = root / "sec_top_moat.csv"
    moat_core_csv = root / "sec_top_moat_core.csv"
    moat_emerging_csv = root / "sec_top_moat_emerging.csv"
    clean_gappers_csv = root / "sec_clean_gappers.csv"
    clean_value_csv = root / "sec_clean_value.csv"
    clean_moat_core_csv = root / "sec_clean_moat_core.csv"
    outcome_rows_csv = root / "sec_outcome_rows.csv"
    outcome_summary_csv = root / "sec_outcome_summary.csv"
    combined_tickers_file = root / "combined_priority_tickers.txt"
    combined_csv = root / "combined_priority.csv"
    headline_only_csv = root / "headline_only_momentum.csv"
    sector_momentum_csv = root / "news_sector_momentum.csv"
    news_signals_csv = root / "news_signals.csv"
    bbg_used_csv = root / "bloomberg_headlines_used.csv"
    scoring_config_json = root / "scoring_config.json"
    scoring_tuning_log_csv = root / "scoring_tuning_log.csv"

    newsletter_html_file = root / "newsletter_body.html"
    newsletter_premium_html_file = root / "newsletter_body_premium.html"
    newsletter_picks_file = root / "newsletter_picks.json"

    tickers_text = tickers_file.read_text(encoding="utf-8").strip()
    ticker_count = 0 if not tickers_text else len(tickers_text.splitlines())
    momentum_text = momentum_file.read_text(encoding="utf-8").strip() if momentum_file.exists() else ""
    quality_text = quality_file.read_text(encoding="utf-8").strip() if quality_file.exists() else ""
    gappers_text = gappers_file.read_text(encoding="utf-8").strip() if gappers_file.exists() else ""
    value_text = value_file.read_text(encoding="utf-8").strip() if value_file.exists() else ""
    moat_text = moat_file.read_text(encoding="utf-8").strip() if moat_file.exists() else ""
    moat_core_text = moat_core_file.read_text(encoding="utf-8").strip() if moat_core_file.exists() else ""
    moat_emerging_text = (
        moat_emerging_file.read_text(encoding="utf-8").strip() if moat_emerging_file.exists() else ""
    )
    clean_gappers_text = clean_gappers_file.read_text(encoding="utf-8").strip() if clean_gappers_file.exists() else ""
    clean_value_text = clean_value_file.read_text(encoding="utf-8").strip() if clean_value_file.exists() else ""
    clean_moat_core_text = (
        clean_moat_core_file.read_text(encoding="utf-8").strip() if clean_moat_core_file.exists() else ""
    )
    combined_tickers_text = (
        combined_tickers_file.read_text(encoding="utf-8").strip() if combined_tickers_file.exists() else ""
    )

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")

    # ── Newsletter mode: clean HTML email, no CSV attachments ───────────────
    if newsletter_mode and newsletter_html_file.exists():

        # PREMIUM_ONLY=1 runs at 3:45 AM before the 4:15 AM free-body rebuild.
        # The free body is legitimately stale at that hour, so skip the free-body
        # guards. The premium body has its own freshness guard at the send step.
        _premium_only_mode = os.getenv("PREMIUM_ONLY", "").strip() == "1"

        # ── GUARD 1: FRESHNESS — refuse to send a stale newsletter ──────────
        # Use CONTENT check (not mtime) — GitHub Actions cache restore resets
        # file timestamps to "now", making mtime-based checks useless there.
        import os as _os
        today_date = dt.date.today()
        today_str = today_date.isoformat()  # e.g. "2026-04-02"
        html_content = newsletter_html_file.read_text(encoding="utf-8", errors="replace")
        # Check for ISO stamp injected by build_newsletter_picks.py
        if not _premium_only_mode and f"newsletter-date:{today_str}" not in html_content:
            html_mtime = dt.date.fromtimestamp(_os.path.getmtime(newsletter_html_file))
            print(
                f"ABORT: newsletter_body.html does not contain today's stamp "
                f"(newsletter-date:{today_str}). File mtime={html_mtime}. "
                "Refusing to send stale content."
            )
            return 1

        # ── GUARD 2: MINIMUM SIZE — reject empty/broken newsletters ─────────
        html_size = newsletter_html_file.stat().st_size
        MIN_NEWSLETTER_BYTES = 15_000   # a real newsletter is >50KB; 15KB catches error pages
        if not _premium_only_mode and html_size < MIN_NEWSLETTER_BYTES:
            print(
                f"ABORT: newsletter_body.html is only {html_size:,} bytes "
                f"(minimum {MIN_NEWSLETTER_BYTES:,}). Content appears incomplete. "
                "Refusing to send."
            )
            return 1
        # ─────────────────────────────────────────────────────────────────────

        picks = {}
        if newsletter_picks_file.exists():
            try:
                picks = json.loads(newsletter_picks_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                picks = {}
        top_pick = picks.get("top_pick", "")
        date_label = today_date.isoformat()
        subject_file = root / "newsletter_subject.txt"
        if subject_file.exists():
            subject_mtime = dt.date.fromtimestamp(subject_file.stat().st_mtime)
            if subject_mtime == today_date:
                subject = subject_file.read_text(encoding="utf-8").strip()
                print(f"  using compelling subject: {subject}")
            else:
                print(
                    "  stale compelling subject ignored: "
                    f"{subject_file.name} mtime={subject_mtime} expected={today_date}"
                )
                subject = ""
        elif top_pick:
            subject = f"SEC Catalyst Daily — {date_label} | Top Pick: {top_pick}"
        else:
            subject = f"SEC Catalyst Daily — {date_label}"
        if not subject:
            if top_pick:
                subject = f"SEC Catalyst Daily — {date_label} | Top Pick: {top_pick}"
            else:
                subject = f"SEC Catalyst Daily — {date_label}"

        html_body = newsletter_html_file.read_text(encoding="utf-8")
        plain_body = (
            f"SEC Catalyst Daily — {date_label}\n"
            f"Generated: {now}\n\n"
            f"Top Pick: {top_pick}\n"
            f"Gapper picks: {picks.get('gapper_count', 0)}\n"
            f"Value picks:  {picks.get('value_count', 0)}\n"
            f"Moat picks:   {picks.get('moat_count', 0)}\n\n"
            "View the full newsletter in your HTML email client."
        )

        # Premium subscriber list (paid — manually maintained in PREMIUM_EMAIL_TO)
        premium_email_to = os.getenv("PREMIUM_EMAIL_TO", "").strip()
        premium_recipients: list[str] = [e.strip() for e in premium_email_to.split(",") if e.strip()]
        premium_set: set[str] = {e.lower() for e in premium_recipients}

        # Build free recipient list from subscribers.json + EMAIL_TO
        subscribers_file = root / "subscribers.json"
        recipients: list[str] = []

        if subscribers_file.exists():
            try:
                subs_data = json.loads(subscribers_file.read_text(encoding="utf-8"))
                all_subs = [s.get("email", "").strip() for s in subs_data if s.get("active", True)]
                recipients = [e for e in all_subs if e and e.lower() not in premium_set]
                print(f"Loaded {len(all_subs)} subscribers from subscribers.json, {len(recipients)} free, {len(premium_recipients)} premium")
            except (json.JSONDecodeError, KeyError) as exc:
                print(f"WARNING: Failed to parse subscribers.json: {exc}")

        if not recipients and email_to:
            raw_fallback = [e.strip() for e in email_to.split(",") if e.strip()]
            recipients = [e for e in raw_fallback if e.lower() not in premium_set]
            excluded = len(raw_fallback) - len(recipients)
            print(
                f"Using EMAIL_TO fallback: {len(recipients)} recipients"
                + (f" ({excluded} excluded — already on premium list)" if excluded else "")
            )

        if not recipients and not premium_recipients:
            print(
                "ABORT: no newsletter recipients found. "
                "subscribers.json is empty and EMAIL_TO fallback is unset."
            )
            return 1

        # PREMIUM_ONLY=1 — pipeline run at 3:30am ET, sends premium only
        # FREE_ONLY=1   — free-email job at 4:05am ET, sends free only (skips premium)
        # default       — sends both (manual runs / local testing)
        premium_only = os.getenv("PREMIUM_ONLY", "").strip() == "1"
        free_only    = os.getenv("FREE_ONLY",    "").strip() == "1"

        # Delivery tracking — record sent/failed per recipient
        delivery_log = root / f"delivery_log_{date_label}.txt"
        sent_ok:   list[str] = []
        sent_fail: list[str] = []

        try:
            smtp_cm = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
        except OSError as exc:
            print(f"ABORT: could not reach SMTP server {smtp_host}:{smtp_port} - {exc}")
            if smtp_host.endswith("gmail.com") and smtp_port in {25, 465, 587}:
                print(
                    "HINT: common cloud providers block outbound Gmail SMTP ports. "
                    "Use a transactional provider/API or a reachable SMTP port."
                )
            return 1

        try:
            with smtp_cm as smtp:
                if use_tls:
                    smtp.starttls()
                smtp.login(smtp_user, smtp_pass)

                # Send premium version to paid subscribers (skip if FREE_ONLY)
                if premium_recipients and newsletter_premium_html_file.exists() and not free_only:
                    premium_html = newsletter_premium_html_file.read_text(encoding="utf-8")
                    # ── GUARD: premium body freshness ──────────────────────────
                    if f"newsletter-date:{today_str}" not in premium_html:
                        prem_mtime = dt.date.fromtimestamp(
                            _os.path.getmtime(newsletter_premium_html_file)
                        )
                        print(
                            f"ABORT: newsletter_body_premium.html does not contain "
                            f"today's stamp (newsletter-date:{today_str}). "
                            f"File mtime={prem_mtime}. Refusing to send stale premium."
                        )
                        return 1
                    # ───────────────────────────────────────────────────────────
                    premium_subject = subject + " - Premium"
                    for recipient in premium_recipients:
                        try:
                            msg = EmailMessage()
                            msg["From"] = email_from
                            msg["To"] = recipient
                            msg["Subject"] = premium_subject
                            msg.set_content(plain_body)
                            msg.add_alternative(premium_html, subtype="html")
                            smtp.send_message(msg)
                            sent_ok.append(f"[premium] {recipient}")
                        except Exception as exc:
                            sent_fail.append(f"[premium] {recipient} - {exc}")
                            print(f"  WARN: failed to send premium to {recipient}: {exc}")
                    print(f"premium_sent ok={len([x for x in sent_ok if 'premium' in x])} "
                          f"fail={len([x for x in sent_fail if 'premium' in x])}")

                # Send free version (skip when running in PREMIUM_ONLY mode)
                if not premium_only and not free_only or free_only:
                    for recipient in recipients:
                        try:
                            msg = EmailMessage()
                            msg["From"] = email_from
                            msg["To"] = recipient
                            msg["Subject"] = subject
                            msg.set_content(plain_body)
                            msg.add_alternative(html_body, subtype="html")
                            smtp.send_message(msg)
                            sent_ok.append(f"[free] {recipient}")
                        except Exception as exc:
                            sent_fail.append(f"[free] {recipient} - {exc}")
                            print(f"  WARN: failed to send to {recipient}: {exc}")
                    free_ok = len([x for x in sent_ok if "[free]" in x])
                    print(f"newsletter_sent ok={free_ok}/{len(recipients)} subject={subject}")
                else:
                    print("premium_only mode - free email deferred to 4:05 AM ET job")
        except Exception as exc:
            print(f"ABORT: SMTP session failed - {exc}")
            return 1

        # ── DELIVERY RECEIPT — written regardless of individual failures ──────
        receipt_lines = [
            f"date={date_label}",
            f"subject={subject}",
            f"html_size={html_size:,} bytes",
            f"sent_ok={len(sent_ok)}",
            f"sent_fail={len(sent_fail)}",
        ] + [f"  OK  {r}" for r in sent_ok] + [f"  FAIL {r}" for r in sent_fail]
        delivery_log.write_text("\n".join(receipt_lines) + "\n", encoding="utf-8")
        print(f"delivery_receipt written → {delivery_log.name}")
        # ─────────────────────────────────────────────────────────────────────

        # Return non-zero if any delivery failed so the shell script can flag it
        return 0 if not sent_fail else 2

    if not email_to:
        raise RuntimeError("Missing required environment variable: EMAIL_TO")

    # ── Internal mode: plain text + all CSV attachments (default) ───────────
    subject = f"SEC Catalyst List ({ticker_count} tickers) - {dt.date.today().isoformat()}"

    msg = EmailMessage()
    msg["From"] = email_from
    msg["To"] = email_to
    msg["Subject"] = subject

    body = [
        f"Generated: {now}",
        f"Ticker count: {ticker_count}",
        "",
        "Top tickers (base list):",
    ]
    body.extend(tickers_text.splitlines()[:40] if tickers_text else ["(none)"])
    body.extend(
        [
            "",
            "Top momentum (first 20):",
        ]
    )
    body.extend(momentum_text.splitlines()[:20] if momentum_text else ["(none)"])
    body.extend(
        [
            "",
            "Top quality (first 20):",
        ]
    )
    body.extend(quality_text.splitlines()[:20] if quality_text else ["(none)"])
    body.extend(
        [
            "",
            "Top gappers (first 20):",
        ]
    )
    body.extend(gappers_text.splitlines()[:20] if gappers_text else ["(none)"])
    body.extend(
        [
            "",
            "Top value (first 20):",
        ]
    )
    body.extend(value_text.splitlines()[:20] if value_text else ["(none)"])
    body.extend(
        [
            "",
            "Clean gappers preset (first 20):",
        ]
    )
    body.extend(clean_gappers_text.splitlines()[:20] if clean_gappers_text else ["(none)"])
    body.extend(
        [
            "",
            "Clean value preset (first 20):",
        ]
    )
    body.extend(clean_value_text.splitlines()[:20] if clean_value_text else ["(none)"])
    body.extend(
        [
            "",
            "Clean moat core preset (first 20):",
        ]
    )
    body.extend(clean_moat_core_text.splitlines()[:20] if clean_moat_core_text else ["(none)"])
    body.extend(
        [
            "",
            "Combined SEC + News priority (first 25):",
        ]
    )
    body.extend(combined_tickers_text.splitlines()[:25] if combined_tickers_text else ["(none)"])
    body.extend(
        [
            "",
            "Top moat (first 20):",
        ]
    )
    body.extend(moat_text.splitlines()[:20] if moat_text else ["(none)"])
    body.extend(
        [
            "",
            "Top moat core (first 20):",
        ]
    )
    body.extend(moat_core_text.splitlines()[:20] if moat_core_text else ["(none)"])
    body.extend(
        [
            "",
            "Top moat emerging (first 20):",
        ]
    )
    body.extend(moat_emerging_text.splitlines()[:20] if moat_emerging_text else ["(none)"])
    body.append("")
    if outcome_summary_csv.exists():
        try:
            lines = outcome_summary_csv.read_text(encoding="utf-8").strip().splitlines()
            body.append("Recent outcome summary:")
            body.extend(lines[:8] if lines else ["(none)"])
            body.append("")
        except OSError:
            pass
    body.append("")
    body.append("Full files are attached.")
    msg.set_content("\n".join(body))

    msg.add_attachment(
        tickers_file.read_bytes(),
        maintype="text",
        subtype="plain",
        filename=tickers_file.name,
    )
    msg.add_attachment(
        csv_file.read_bytes(),
        maintype="text",
        subtype="csv",
        filename=csv_file.name,
    )
    if momentum_file.exists():
        msg.add_attachment(
            momentum_file.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=momentum_file.name,
        )
    if quality_file.exists():
        msg.add_attachment(
            quality_file.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=quality_file.name,
        )
    if momentum_csv.exists():
        msg.add_attachment(
            momentum_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=momentum_csv.name,
        )
    if quality_csv.exists():
        msg.add_attachment(
            quality_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=quality_csv.name,
        )
    if gappers_file.exists():
        msg.add_attachment(
            gappers_file.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=gappers_file.name,
        )
    if value_file.exists():
        msg.add_attachment(
            value_file.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=value_file.name,
        )
    if moat_file.exists():
        msg.add_attachment(
            moat_file.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=moat_file.name,
        )
    if moat_core_file.exists():
        msg.add_attachment(
            moat_core_file.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=moat_core_file.name,
        )
    if moat_emerging_file.exists():
        msg.add_attachment(
            moat_emerging_file.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=moat_emerging_file.name,
        )
    if clean_gappers_file.exists():
        msg.add_attachment(
            clean_gappers_file.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=clean_gappers_file.name,
        )
    if clean_value_file.exists():
        msg.add_attachment(
            clean_value_file.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=clean_value_file.name,
        )
    if clean_moat_core_file.exists():
        msg.add_attachment(
            clean_moat_core_file.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=clean_moat_core_file.name,
        )
    if gappers_csv.exists():
        msg.add_attachment(
            gappers_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=gappers_csv.name,
        )
    if value_csv.exists():
        msg.add_attachment(
            value_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=value_csv.name,
        )
    if moat_csv.exists():
        msg.add_attachment(
            moat_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=moat_csv.name,
        )
    if moat_core_csv.exists():
        msg.add_attachment(
            moat_core_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=moat_core_csv.name,
        )
    if moat_emerging_csv.exists():
        msg.add_attachment(
            moat_emerging_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=moat_emerging_csv.name,
        )
    if clean_gappers_csv.exists():
        msg.add_attachment(
            clean_gappers_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=clean_gappers_csv.name,
        )
    if clean_value_csv.exists():
        msg.add_attachment(
            clean_value_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=clean_value_csv.name,
        )
    if clean_moat_core_csv.exists():
        msg.add_attachment(
            clean_moat_core_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=clean_moat_core_csv.name,
        )
    if outcome_rows_csv.exists():
        msg.add_attachment(
            outcome_rows_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=outcome_rows_csv.name,
        )
    if outcome_summary_csv.exists():
        msg.add_attachment(
            outcome_summary_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=outcome_summary_csv.name,
        )
    if combined_tickers_file.exists():
        msg.add_attachment(
            combined_tickers_file.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=combined_tickers_file.name,
        )
    if combined_csv.exists():
        msg.add_attachment(
            combined_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=combined_csv.name,
        )
    if headline_only_csv.exists():
        msg.add_attachment(
            headline_only_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=headline_only_csv.name,
        )
    if sector_momentum_csv.exists():
        msg.add_attachment(
            sector_momentum_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=sector_momentum_csv.name,
        )
    if news_signals_csv.exists():
        msg.add_attachment(
            news_signals_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=news_signals_csv.name,
        )
    if bbg_used_csv.exists():
        msg.add_attachment(
            bbg_used_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=bbg_used_csv.name,
        )
    if scoring_config_json.exists():
        msg.add_attachment(
            scoring_config_json.read_bytes(),
            maintype="application",
            subtype="json",
            filename=scoring_config_json.name,
        )
    if scoring_tuning_log_csv.exists():
        msg.add_attachment(
            scoring_tuning_log_csv.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=scoring_tuning_log_csv.name,
        )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        smtp.login(smtp_user, smtp_pass)
        smtp.send_message(msg)
    print(f"email_sent to={email_to} subject={subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
