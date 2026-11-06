"""Treat summaries, model output, subjects and sender strings as hostile display text."""
import html
import re
from datetime import datetime
from urllib.parse import quote

_SECRET = re.compile(r"(?i)(?:\b(?:otp|(?:verification|authentication|security|login|sign.in|reset|one.time|recovery)[ -]?(?:code|token|password))\s*(?:is|:|=)?\s*[:=]?\s*[A-Z0-9-]{4,}\b|\b(?:password|passwd|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|authorization)\s*[:=]\s*\S+|\b(?:sk-|ghp_|github_pat_|AKIA)[A-Za-z0-9_-]{12,}|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_.-]+|-----BEGIN[^-]*PRIVATE KEY-----[\s\S]*?(?:-----END[^-]*PRIVATE KEY-----|$))")
_URL = re.compile(r"(?i)(?:https?://|www\.)\S+")


def redact(value, limit=2000):
    text = _SECRET.sub("[redacted secret]", str(value or ""))
    # Explicit valid calendar timestamps are useful deadlines, not standalone
    # numeric codes. Secret-labelled values were removed above, before this step.
    dates = {}
    def calendar(match):
        try:
            datetime.fromisoformat(match[0].replace('Z', '+00:00'))
        except ValueError:
            return match[0]
        marker = 'STEWARDCALENDARDATE' + chr(65 + len(dates)) + 'END'
        dates[marker] = match[0]
        return marker
    text = re.sub(r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})\b', calendar, text)
    # Unknown numbers may be a standalone authentication code. Conservatively redact.
    text = re.sub(r"\b\d{4,10}\b", "[redacted number]", text)
    for marker, date in dates.items():
        text = text.replace(marker, date)
    text = _URL.sub("[link removed]", text)
    text = "".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and c not in "\u202a\u202b\u202d\u202e\u2066\u2067\u2068\u2069"))
    return text if limit is None else text[:limit]


def safe(value, limit=2000):
    text = html.escape(redact(value, limit), quote=True).replace("@", "＠")
    # Hermes' outbound surface interprets MEDIA:/path and local file paths. Mail can never emit them.
    text = re.sub(r"(?i)\bMEDIA\s*:", "MEDIA：", text).replace("/", "／").replace("\\", "＼")
    return re.sub(r"([\\`*_{}\[\]()|>~])", r"\\\1", text)


def gmail_link(address, thread):
    return "https://mail.google.com/mail/u/?authuser=" + quote(address, safe="") + "#all/" + quote(thread, safe="")
