#!/usr/bin/env python3
"""build_localized_pages.py — generate static localized landing pages.

Reads:
  i18n/translations.json — source-of-truth strings + per-locale translations
  i18n/template_landing.html — template with {{key}} placeholders

Writes (per locale):
  docs/{locale}/index.html — fully localized landing page

Each generated page emits:
  - <html lang="...">  with optional dir="rtl" for Arabic/Hebrew
  - <link rel="alternate" hreflang="..."> chain for every supported locale
  - Translated meta tags (title, description, og:locale)
  - Translated body content

English source ('en') is NOT regenerated — that lives at /landing/index.html.
We only generate the non-English variants under /<locale>/.

Run:
  python3 build_localized_pages.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _find_root() -> Path:
    for cand in (
        Path("/opt/catalyst"),
        Path("/home/operator/.openclaw/workspace"),
        Path(__file__).resolve().parent,
    ):
        if (cand / "build_localized_pages.py").exists():
            return cand
    return Path(__file__).resolve().parent


ROOT = _find_root()
TRANS_PATH = ROOT / "i18n" / "translations.json"
TEMPLATE_PATH = ROOT / "i18n" / "template_landing.html"
DOCS = ROOT / "docs"

# Locale → URL path mapping (RFC 5646 BCP 47 → URL-safe slug)
LOCALE_PATHS = {
    "en":    "",          # English at root, no path
    "es":    "es",
    "pt-BR": "pt-br",
    "hi":    "hi",
    "zh-CN": "zh",
    "ja":    "ja",
    "de":    "de",
    "ar":    "ar",
    "fr":    "fr",
    "ko":    "ko",
}

# OpenGraph locale codes (en_US, es_ES style)
OG_LOCALES = {
    "en":    "en_US",
    "es":    "es_ES",
    "pt-BR": "pt_BR",
    "hi":    "hi_IN",
    "zh-CN": "zh_CN",
    "ja":    "ja_JP",
    "de":    "de_DE",
    "ar":    "ar_AE",
    "fr":    "fr_FR",
    "ko":    "ko_KR",
}

RTL_LOCALES = {"ar", "he", "fa", "ur"}


def hreflang_tags_for(supported: list[str], default: str = "en") -> str:
    """Build a full hreflang chain including x-default."""
    out = []
    base = "https://catalystedgescanner.com"
    out.append(f'<link rel="alternate" hreflang="x-default" href="{base}/">')
    for loc in supported:
        path = LOCALE_PATHS.get(loc, loc)
        href = f"{base}/" if not path else f"{base}/{path}/"
        out.append(f'<link rel="alternate" hreflang="{loc}" href="{href}">')
    return "\n".join(out)


def render(template: str, ctx: dict) -> str:
    """Replace {{key}} placeholders. Falls back to empty string when missing."""
    pattern = re.compile(r"\{\{\s*(\w+)\s*\}\}")
    return pattern.sub(lambda m: str(ctx.get(m.group(1), "")), template)


def main() -> int:
    if not TRANS_PATH.exists() or not TEMPLATE_PATH.exists():
        print(f"missing source files: {TRANS_PATH} / {TEMPLATE_PATH}")
        return 1

    data = json.loads(TRANS_PATH.read_text(encoding="utf-8"))
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    base_strings = data.get("strings", {})
    translations = data.get("translations", {})
    supported = data.get("supported_locales", ["en"])

    hreflang_block = hreflang_tags_for(supported)
    written = 0

    for locale in supported:
        if locale == "en":
            continue  # English source lives at /landing/, not /en/
        if locale not in translations:
            print(f"  skip {locale}: no translations defined")
            continue

        # Merge: start with English source, overlay locale-specific keys
        ctx = dict(base_strings)
        ctx.update(translations[locale])
        ctx["locale_path"] = LOCALE_PATHS.get(locale, locale)
        ctx["og_locale"] = OG_LOCALES.get(locale, "en_US")
        ctx["hreflang_tags"] = hreflang_block
        ctx["rtl_attr"] = 'dir="rtl"' if locale.split("-")[0] in RTL_LOCALES else ""

        out_dir = DOCS / LOCALE_PATHS[locale]
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "index.html"
        out_file.write_text(render(template, ctx), encoding="utf-8")
        written += 1
        print(f"  wrote {locale} → /{ctx['locale_path']}/index.html "
              f"({out_file.stat().st_size} bytes)")

    print(f"build_localized_pages: {written} locales generated")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
