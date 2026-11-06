"""Gmail REST transport. Hermes owns distinct per-slot OAuth grants and refresh."""
from dataclasses import dataclass, field
import base64
from html.parser import HTMLParser
import re
from urllib.parse import quote, urlencode

from .errors import Error

BASE = "https://gmail.googleapis.com/gmail/v1/users/"
GRANTS = ("gmail-1", "gmail-2", "gmail-3", "gmail-4")
MAX_BODY = 32000
MAX_ATTACHMENTS = 20
MAX_BYTES = 16 * 1024 * 1024
MAX_LIST = 2000


def bounded_content(parts, limit=MAX_BODY):
    """Budget the final joined representation, including inserted separators."""
    joined = "\n".join(part for part in parts if part)
    return joined[:limit], len(joined) > limit


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value):
        raise Error("provider_invalid", "Provider returned an invalid identifier.", 503)
    return quote(value, safe="")


def decode(data, limit=MAX_BYTES):
    if not isinstance(data, str) or len(data) > limit * 4 // 3 + 8:
        raise Error("content_limit", "Provider content exceeds the bounded input limit.", 503)
    try:
        result = base64.b64decode(data + "=" * (-len(data) % 4), altchars=b"-_", validate=True)
    except ValueError:
        raise Error("provider_invalid", "Provider returned malformed content.", 503) from None
    if len(result) > limit:
        raise Error("content_limit", "Provider content exceeds the bounded input limit.", 503)
    return result


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        if tag in {"br", "p", "div", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


@dataclass
class Attachment:
    filename: str
    content_type: str
    size: int
    load: object


@dataclass
class Message:
    id: str
    thread_id: str
    sender: str
    subject: str
    body: str
    received: float
    inbox: bool
    unread: bool
    sent: bool = False
    excluded: bool = False
    attachments: list[Attachment] = field(default_factory=list)
    content_hold: bool = False


class Gmail:
    def __init__(self, grant_id, request=None, *, expected_address):
        if grant_id not in GRANTS:
            raise Error("grant_invalid", "Select one of the declared Gmail grant slots.", 422)
        self.grant_id = grant_id
        if (not isinstance(expected_address, str) or len(expected_address) > 320
                or expected_address.count("@") != 1 or not all(expected_address.split("@"))):
            raise Error("account_required", "An explicit receiving mailbox is required.", 422)
        # Provider-side user addressing is the authority boundary even if the
        # host resolves a different bearer between profile and resource calls.
        self._base = BASE + quote(expected_address.casefold(), safe="")
        self.request = request or self._host_request
        self._triaged = None

    @staticmethod
    def _host_request(provider, method, url, **kwargs):
        from hermes_cli.plugin_provider_requests import credentialed_provider_request
        return credentialed_provider_request(provider, method, url, **kwargs)

    def call(self, method, path, *, params=None, body=None):
        url = self._base + path + ("?" + urlencode(params) if params else "")
        try:
            response = self.request(self.grant_id, method, url, json=body, timeout=20)
        except Exception:
            raise Error("provider_unavailable", "Gmail request failed. Check this profile's grant and retry; no content was logged.", 503) from None
        if response.status == 404:
            raise Error("provider_not_found", "Gmail resource or history cursor is unavailable.", 503)
        if response.status == 403:
            raise Error("account_access_denied", "Gmail refused access to the bound receiving mailbox; operation retained for review/retry.", 403)
        if response.status < 200 or response.status >= 300:
            raise Error("provider_unavailable", "Gmail returned an unsuccessful response; work remains pending.", 503)
        if len(response.body) > 40 * 1024 * 1024:
            raise Error("content_limit", "Gmail response exceeds the transport limit.", 503)
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError
            return result
        except (ValueError, TypeError):
            raise Error("provider_invalid", "Gmail returned invalid JSON.", 503) from None

    def profile(self):
        data = self.call("GET", "/profile")
        return {"address": data["emailAddress"], "checkpoint": str(data["historyId"])}

    def changes(self, checkpoint):
        ids, token, final = set(), None, checkpoint
        for _ in range(100):
            params = {"startHistoryId": checkpoint, "maxResults": 100, "historyTypes": "messageAdded"}
            if token:
                params["pageToken"] = token
            data = self.call("GET", "/history", params=params)
            for history in data.get("history", []):
                ids.update(x["message"]["id"] for x in history.get("messagesAdded", []))
            if len(ids) > MAX_LIST:
                raise Error("intake_limit", "Intake batch is too large; checkpoint retained. Run a bounded historical operation.", 503)
            final, token = str(data.get("historyId", final)), data.get("nextPageToken")
            if not token:
                return sorted(ids), final
        raise Error("intake_limit", "History pagination limit exceeded; checkpoint retained.", 503)

    def historical(self, after, before, limit):
        query = "in:inbox -in:spam -in:trash after:" + str(int(after)) + " before:" + str(int(before))
        ids, token = [], None
        for _ in range(25):
            params = {"q": query, "maxResults": min(limit + 1 - len(ids), 100)}
            if token:
                params["pageToken"] = token
            data = self.call("GET", "/messages", params=params)
            ids.extend(x["id"] for x in data.get("messages", []))
            token = data.get("nextPageToken")
            if len(ids) > limit or (len(ids) == limit and token):
                raise Error("historical_limit", "Scope exceeds its message limit; narrow the date range. Nothing queued.", 422)
            if not token:
                return ids
        raise Error("historical_limit", "Historical pagination limit exceeded.", 422)

    def fetch(self, ident):
        data = self.call("GET", "/messages/" + identifier(ident), params={"format": "full"})
        labels = set(data.get("labelIds", []))
        headers = {h["name"].casefold(): h["value"] for h in data.get("payload", {}).get("headers", [])}
        text, html, attachments, hold = [], [], [], False
        stack, visited, total_text = [data.get("payload", {})], 0, 0
        while stack:
            part = stack.pop()
            visited += 1
            if visited > 100:
                hold = True
                break
            if len(stack) + len(part.get("parts", [])) > 100:
                hold = True
                break
            stack.extend(reversed(part.get("parts", [])))
            mime, name, body = part.get("mimeType", ""), part.get("filename", ""), part.get("body", {})
            if name or body.get("attachmentId"):
                if len(attachments) >= MAX_ATTACHMENTS:
                    hold = True
                    continue
                attachment_id, inline = body.get("attachmentId"), body.get("data", "")
                def load(aid=attachment_id, raw=inline):
                    if aid:
                        raw = self.call("GET", "/messages/" + identifier(ident) + "/attachments/" + identifier(aid)).get("data", "")
                    return decode(raw)
                attachments.append(Attachment(name or "unnamed", mime, int(body.get("size", 0)), load))
            elif mime in {"text/plain", "text/html"} and body.get("data"):
                decoded = decode(body["data"], MAX_BYTES).decode("utf-8", "replace")
                total_text += len(decoded)
                if total_text > MAX_BODY:
                    hold = True
                (text if mime == "text/plain" else html).append(decoded[:MAX_BODY])
        if text:
            content, clipped = bounded_content(text)
            hold = hold or clipped
        else:
            parser = PlainHTML()
            raw_html, clipped = bounded_content(html)
            parser.feed(raw_html)
            rendered = "".join(parser.parts)
            content = rendered[:MAX_BODY]
            hold = hold or clipped or len(rendered) > MAX_BODY
        return Message(str(data["id"]), str(data["threadId"]), headers.get("from", "")[:320],
                       headers.get("subject", "")[:1000], content, int(data.get("internalDate", "0")) / 1000,
                       "INBOX" in labels, "UNREAD" in labels, "SENT" in labels,
                       bool(labels & {"SPAM", "TRASH"}), attachments, hold)

    def triaged_label(self):
        if self._triaged:
            return self._triaged
        labels = self.call("GET", "/labels").get("labels", [])
        existing = next((l["id"] for l in labels if l["name"] == "Triaged"), None)
        if existing is None:
            existing = self.call("POST", "/labels", body={"name": "Triaged", "labelListVisibility": "labelShow", "messageListVisibility": "show"})["id"]
        self._triaged = existing
        return existing

    def mark_triaged(self, ident):
        self.call("POST", "/messages/" + identifier(ident) + "/modify", body={"addLabelIds": [self.triaged_label()], "removeLabelIds": []})

    def archive(self, thread, archived):
        self.call("POST", "/threads/" + identifier(thread) + "/modify", body={
            "addLabelIds": [] if archived else ["INBOX"], "removeLabelIds": ["INBOX"] if archived else []})

    def archive_message(self, ident):
        """Automatic effects touch only the assessed incoming message."""
        self.call("POST", "/messages/" + identifier(ident) + "/modify",
                  body={"addLabelIds": [], "removeLabelIds": ["INBOX"]})

    def thread_state(self, thread):
        result = self.call("GET", "/threads/" + identifier(thread), params={"format": "metadata"})
        messages = result.get("messages", [])
        return {"inbox": any("INBOX" in m.get("labelIds", []) for m in messages),
                "sent_at": max((int(m.get("internalDate", 0)) / 1000 for m in messages if "SENT" in m.get("labelIds", [])), default=0)}
