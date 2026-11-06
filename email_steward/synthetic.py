"""Explicitly synthetic local provider/model/delivery; never selected by native registration."""
from .gmail import Message, Attachment
from .errors import Error


class SyntheticGmail:
    def __init__(self, address="alex@example.test"):
        self.address, self.messages, self.sequence = address, {}, 0
        self.fail_modify = 0
        self.fail_changes = False
        self.modifications = []

    def profile(self):
        return {"address": self.address, "checkpoint": str(self.sequence)}

    def add(self, ident, *, thread=None, subject="Synthetic message", body="Synthetic body", unread=True,
            historical=False, attachments=(), received=900):
        self.sequence += 1
        self.messages[ident] = dict(id=ident, thread=thread or ident, subject=subject, body=body,
            unread=unread, labels={"INBOX"}, sequence=-1 if historical else self.sequence,
            attachments=list(attachments), received=received)

    def changes(self, checkpoint):
        if self.fail_changes:
            raise Error("provider_unavailable", "Synthetic provider failure", 503)
        return [i for i, m in self.messages.items() if m["sequence"] > int(checkpoint)], str(self.sequence)

    def fetch(self, ident):
        m = self.messages[ident]
        return Message(ident, m["thread"], "synthetic@example.test", m["subject"], m["body"], m["received"],
                       "INBOX" in m["labels"], m["unread"], "SENT" in m["labels"], False, m["attachments"])

    def mark_triaged(self, ident):
        if self.fail_modify:
            self.fail_modify -= 1
            raise Error("provider_unavailable", "Synthetic modify failure", 503)
        self.messages[ident]["labels"].add("Triaged")
        self.modifications.append((ident, "Triaged"))

    def archive(self, thread, archived):
        if self.fail_modify:
            self.fail_modify -= 1
            raise Error("provider_unavailable", "Synthetic modify failure", 503)
        for m in self.messages.values():
            if m["thread"] == thread:
                m["labels"].discard("INBOX") if archived else m["labels"].add("INBOX")
        self.modifications.append((thread, "archive" if archived else "restore"))

    def archive_message(self, ident):
        if self.fail_modify:
            self.fail_modify -= 1
            raise Error("provider_unavailable", "Synthetic modify failure", 503)
        self.messages[ident]["labels"].discard("INBOX")
        self.modifications.append((ident, "archive_message"))

    def thread_state(self, thread):
        messages = [m for m in self.messages.values() if m["thread"] == thread]
        return {"inbox": any("INBOX" in m["labels"] for m in messages),
                "sent_at": max((m["received"] for m in messages if "SENT" in m["labels"]), default=0)}

    def historical(self, after, before, limit):
        ids = [i for i, m in self.messages.items() if after <= m["received"] < before and "INBOX" in m["labels"]]
        if len(ids) > limit:
            raise Error("historical_limit", "Narrow synthetic date scope", 422)
        return ids


class SyntheticModel:
    def __init__(self):
        self.calls = []
        self.failure = False

    def judge(self, sample):
        self.calls.append(sample)
        if self.failure:
            raise Error("model_unavailable", "Synthetic model failure", 503)
        return dict(classification="needs_review", archive=False, urgent=False,
                    summary="Synthetic configured-model assessment", reason="Synthetic fixture uncertainty", deadline=None)


class SyntheticDelivery:
    def __init__(self):
        self.sent = []
        self.failure = False
        self.uncertain = False

    def send(self, settings, text, ident):
        settings.require_private()
        if self.failure:
            return "retry"
        self.sent.append((settings.destination, ident, text))
        return "uncertain" if self.uncertain else "sent"
