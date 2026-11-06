"""Bounded durable plaintext and honest native-host delivery receipts."""
import html
import re
import unicodedata

from .presentation import redact

BUDGET = 900  # UTF-8 bytes; leaves headroom for native escaping and ordinary adapter envelopes.


def chunks(text, trusted_links=()):
    text = str(text)
    links = {}
    for index, link in enumerate(trusted_links):
        if link in text:
            marker = "STEWARDTRUSTEDLINK" + chr(65 + index) + "END"
            links[marker] = link
            text = text.replace(link, marker)
    # Existing summaries are escaped for display; decode once, then neutralise every dialect.
    text = html.unescape(text)
    text = redact(text, None)
    text = re.sub(r"\\([`*_{}\[\]()|>~])", r"\1", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = "".join(c for c in text if c == "\n" or unicodedata.category(c) not in {"Cc", "Cf", "Cs"})
    # BlueBubbles emits a separate message per blank-line paragraph. Keep each
    # plugin-owned payload one paragraph so a final receipt cannot hide prefixes.
    text = text.translate(str.maketrans({"@": "＠", "<": "＜", ">": "＞", "`": "｀", "*": "＊",
        "_": "＿", "[": "［", "]": "］", "{": "｛", "}": "｝", "|": "｜", "\\": "＼", "/": "／"}))
    text = re.sub(r"(?im)\b(media|voice|audio|file|bcc|cc|to|subject|from)\s*:", r"\1：", text)
    for marker, link in links.items():
        text = text.replace(marker, link)
    # Pack logical blocks, not unrelated lines. Oversized items repeat their
    # permanent reference on every continuation; no part borrows another item's ID.
    limit = BUDGET - 140
    parts, current = [], ""
    digest = re.search(r"\bD[0-9a-f]{12}\b", text)
    for block in re.split(r"\n[ \t]*\n", text):
        block = block.strip()
        if not block:
            continue
        ref = re.search(r"\b[a-z]{2}\d{1,19}\b", block.split("\n", 1)[0])
        continuation = (ref[0] + " · continued\n") if ref else "Continued\n"
        segments, segment = [], ""
        for line in block.splitlines():
            units = [line + "\n"]
            if len(units[0].encode()) > limit - len(continuation.encode()):
                units = []
                for word in re.findall(r"https://mail\.google\.com/\S+|\S+\s*|\s+", line + "\n"):
                    if len(word.encode()) > limit - len(continuation.encode()):
                        if word.startswith("https://mail.google.com/"):
                            raise ValueError("A trusted link exceeds the bounded native payload; inspect locally")
                        units.extend(word)
                    else:
                        units.append(word)
            for unit in units:
                if len((segment + unit).encode()) > limit:
                    segments.append(segment.rstrip())
                    segment = continuation
                segment += unit
        if segment:
            segments.append(segment.rstrip())
        for segment in segments:
            joined = current + ("\n" if current else "") + segment
            if len(joined.encode()) > limit:
                parts.append(current)
                current = segment
            else:
                current = joined
    if current or not parts:
        parts.append(current or "Email Steward: empty notification held")
    if len(parts) > 1:
        prefix = digest[0] + " · " if digest else ""
        parts = [f"({prefix}part {i + 1}/{len(parts)})\n" + p for i, p in enumerate(parts)]
    return parts


def receipt(result, platform, chat=None):
    """'accepted' means host/provider acknowledgement, never human delivery or read."""
    if not isinstance(result, dict):
        return "uncertain"
    if result.get("platform", platform) != platform or result.get("chat_id", chat) != chat:
        return "uncertain"
    if (result.get("partial") or result.get("partial_success") or result.get("warnings") or result.get("media_dropped")
            or result.get("truncated") or result.get("unconfirmed") or result.get("ambiguous")):
        return "uncertain"
    if result.get("skipped"):
        return "blocked" if (result.get("reason") == "cron_auto_delivery_duplicate_target"
            or platform == "slack" and result.get("skipped") == "empty_text") else "uncertain"
    if result.get("success") is not True or result.get("error"):
        return "uncertain"  # host generic errors do not prove no effect
    if platform in {"ntfy", "wecom", "weixin", "yuanbao"}:
        # These host receipts can expose locally generated/fallback correlation IDs
        # even without a strict provider acknowledgement. Never call them complete.
        return "uncertain"
    ident = result.get("message_id")
    ids = result.get("message_ids")
    valid = lambda value: isinstance(value, (str, int)) and not isinstance(value, bool) and 0 < len(str(value)) <= 512 and str(value).casefold() not in {"none", "null", "unknown", "0", "ok", "pending"}
    if valid(ident):
        if platform in {"discord", "telegram"} and not str(ident).isdigit():
            return "uncertain"
        if platform == "slack" and not re.fullmatch(r"\d+\.\d+", str(ident)):
            return "uncertain"
        if platform == "matrix" and not str(ident).startswith("$"):
            return "uncertain"
        if platform == "google_chat" and not str(ident).startswith(str(chat) + "/messages/"):
            return "uncertain"
    if valid(ident) or isinstance(ids, list) and ids and all(valid(i) for i in ids):
        return "accepted"
    return "uncertain"
