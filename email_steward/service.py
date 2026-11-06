"""Owner-authorised application service shared by Discord, Desktop and CLI."""
from dataclasses import replace
import json
import time

from .errors import Error, invalid
from .gmail import GRANTS, Gmail
from .judgement import CONSENT, DISCLOSURE, preview
from .presentation import gmail_link, redact, safe
from .rules import RuleStore, FIELDS, CLASSIFICATIONS, exact, mutable
from .security import require_access
from .store import dump, private_dir

PUBLIC_ITEM = {"reference", "mailbox_id", "sender", "subject", "summary", "classification", "reason",
               "rule_id", "version", "archived", "attachment_status", "link"}


class Steward:
    def __init__(self, store, settings, provider_factory=None, model=None, settings_reader=None):
        self.store, self.settings = store, settings
        self.provider_factory = provider_factory or (lambda account: Gmail(account["grant_id"], expected_address=account["address"]))
        self.model = model
        self.settings_reader = settings_reader
        self.rule_store = RuleStore(store)

    def current_settings(self):
        try:
            return self._current_settings()
        except Exception:
            with self.store.transaction() as db:
                row = db.execute("SELECT value FROM meta WHERE key='gateway_grant'").fetchone()
                if row:
                    revoked = json.loads(row["value"])
                    if not revoked.get("revoked"):
                        revoked.update(revoked=True, generation=revoked["generation"] + 1)
                        db.execute("UPDATE meta SET value=? WHERE key='gateway_grant'", (dump(revoked),))
                        db.execute("INSERT OR IGNORE INTO meta VALUES(?,?)", ("gateway_grant:" + str(revoked["generation"]), dump(revoked)))
            raise

    def _current_settings(self):
        settings = self.settings_reader() if self.settings_reader else self.settings
        settings.require_private()
        from .gateways import fingerprint, binding as grant_binding
        binding = {"home": str(settings.home), "owner": settings.owner}
        with self.store.transaction() as db:
            row = db.execute("SELECT value FROM meta WHERE key='owner_binding'").fetchone()
            old_binding = json.loads(row["value"]) if row else None
            if old_binding is not None and old_binding != binding and not settings.grant_revision:
                raise Error("owner_binding_mismatch", "State belongs to a different profile owner; use a new private profile or explicit offline migration.", 403)
            if old_binding and old_binding.get("home") != str(settings.home):
                raise Error("owner_binding_mismatch", "State cannot move between profile homes.", 403)
            if row is None:
                db.execute("INSERT INTO meta VALUES('owner_binding',?)", (dump(binding),))
            row = db.execute("SELECT value FROM meta WHERE key='gateway_grant'").fetchone()
            previous = json.loads(row["value"]) if row else None
            revision, fp = settings.grant_revision, fingerprint(settings)
            floor = db.execute("SELECT value FROM meta WHERE key='gateway_revision_floor'").fetchone()
            if floor and revision < json.loads(floor["value"]):
                raise Error("grant_revoked", "Setup is changing or this grant revision has been revoked.", 403)
            if previous and revision < previous["revision"]:
                raise Error("grant_revoked", "An older setup revision cannot restore revoked gateway authority.", 403)
            changed = not previous or previous.get("revoked") or previous["fingerprint"] != fp or previous["revision"] != revision
            generation = (previous["generation"] + 1 if previous else 1) if changed else previous["generation"]
            grant = dict(generation=generation, revision=revision, fingerprint=fp, binding=grant_binding(settings))
            db.execute("INSERT INTO meta VALUES('gateway_grant',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (dump(grant),))
            db.execute("INSERT OR IGNORE INTO meta VALUES(?,?)", ("gateway_grant:" + str(generation), dump(grant)))
            if changed and previous:
                # Content consent is an owner approval, not a property of a mailbox or old route.
                db.execute("INSERT INTO meta VALUES('model_consent','\"\"') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
            # Unbound legacy rows cannot prove their target. Never attach current permission to them.
            db.execute("UPDATE outbox SET state='blocked',error='Unbound legacy delivery quarantined; no reroute' WHERE grant_generation IS NULL AND state IN ('pending','retry')")
        self.store.active_grant = (generation, fp)
        self.store.trusted_links = tuple(gmail_link(a["address"], i["thread_id"])
            for a in self.store.accounts() for i in self.store.items() if i["mailbox_id"] == a["id"])
        return settings

    def guard(self, access):
        self.settings = self.current_settings()
        require_access(self.settings, access)
        if access.grant and access.surface == self.settings.platform:
            self.store.set_meta("gateway_attestation", {"generation": self.store.active_grant[0], "fingerprint": access.grant})

    def provider(self, account):
        provider = self.provider_factory(account)
        # A user may reauthorise a slot between polls. Every item read/mutation
        # must verify the receiving account before using its stored provider IDs.
        if provider.profile()["address"].casefold() != account["address"].casefold():
            raise Error("account_mismatch", "OAuth grant belongs to a different mailbox; operation refused.", 403)
        return provider

    def connect(self, access, grant_id, address, display_name):
        self.guard(access)
        if (grant_id not in GRANTS or not isinstance(address, str) or len(address) > 320
                or address.count("@") != 1 or not all(address.split("@"))
                or not isinstance(display_name, str) or not 1 <= len(display_name) <= 100):
            raise invalid("Use a declared Gmail slot, mailbox address and display name")
        with self.store.operation():
            if any(a["id"] == grant_id or a["address"].casefold() == address.casefold() for a in self.store.accounts()):
                raise Error("already_connected", "Mailbox or grant slot is already connected; baseline was not changed.", 409)
            candidate = dict(id=grant_id, address=address, grant_id=grant_id)
            profile = self.provider(candidate).profile()
            if profile["address"].casefold() != address.casefold():
                raise Error("account_mismatch", "OAuth grant belongs to a different mailbox. Nothing connected.", 403)
            self.store.execute("INSERT INTO accounts(id,address,display_name,grant_id,checkpoint,baseline) VALUES(?,?,?,?,?,?)",
                (grant_id, address, redact(display_name, 100), grant_id, str(profile["checkpoint"]), time.time()))
        return {"mailbox": {"id": grant_id, "address": address, "display_name": redact(display_name, 100)},
                "historical_excluded": True}

    def mailboxes(self, access):
        self.guard(access)
        return [{k: a[k] for k in ("id", "address", "display_name")} for a in self.store.accounts()]

    def rules(self, access):
        self.guard(access)
        return self.rule_store.list()

    def save_rule(self, access, payload, ident=None):
        self.guard(access)
        version = None
        if ident:
            exact(payload, FIELDS | {"version"})
            version, payload = payload["version"], {k: payload[k] for k in FIELDS}
        return self.rule_store.save(payload, ident, version)

    def toggle_rule(self, access, ident, payload):
        self.guard(access)
        return self.rule_store.toggle(ident, payload)

    def packs(self, access):
        self.guard(access)
        return self.rule_store.packs()

    def enable_pack(self, access, ident, payload):
        self.guard(access)
        return self.rule_store.enable_pack(ident, payload)

    def preview(self, access, payload):
        self.guard(access)
        exact(payload, {"rule"}, {"sample", "reference"})
        if ("sample" in payload) == ("reference" in payload):
            raise invalid("Provide exactly one sample or reference")
        rule = self.rule_store.validate(payload["rule"])
        status = "unassessed"
        if "sample" in payload:
            sample = payload["sample"]
            exact(sample, {"mailbox_id", "sender", "subject", "body"})
            if not isinstance(sample["mailbox_id"], str) or sample["mailbox_id"] not in {a["id"] for a in self.store.accounts()}:
                raise invalid("Unknown mailbox")
            for k, limit in (("sender", 320), ("subject", 1000), ("body", 32000)):
                if not isinstance(sample[k], str) or len(sample[k]) > limit:
                    raise invalid("Preview sample exceeds text limits", **{k: "Text is too long or invalid"})
        else:
            item = self.store.item(payload["reference"])
            message = self.provider(self.store.account(item["mailbox_id"])).fetch(item["latest_message"])
            sample = dict(mailbox_id=item["mailbox_id"], sender=message.sender, subject=message.subject, body=message.body)
            status = item["attachment_status"]
            review = item.get("activity_review")
            if review and review["attachment_status"] not in {"none", "ok"}:
                status = review["attachment_status"]
        return preview(rule, sample, status)

    @staticmethod
    def public_item(item):
        return {k: item.get(k) for k in PUBLIC_ITEM}

    def items(self, access):
        self.guard(access)
        return [self.public_item(i) for i in self.store.items()]

    def inspect(self, access, reference, *, text=False, attachments=False):
        self.guard(access)
        item = self.store.item(reference)
        result = {"item": self.public_item(item)}
        review = item.get("activity_review")
        if review:
            result["activity_review"] = review
        if text or attachments:
            message = self.provider(self.store.account(item["mailbox_id"])).fetch(item["latest_message"])
            if text:
                result["text"] = safe(message.body, 12000)
            if attachments:
                messages = [message]
                if review and review["message_id"] != item["latest_message"]:
                    messages.append(self.provider(self.store.account(item["mailbox_id"])).fetch(review["message_id"]))
                from .extraction import extract
                extracts = []
                result["extracts"] = extracts
                for message in messages:
                    for attachment in message.attachments[:max(0, 20-len(extracts))]:
                        extraction = extract(attachment.load(), attachment.filename, attachment.content_type,
                            scratch_root=private_dir(self.store.root / "scratch"))
                        extracts.append({"filename": safe(attachment.filename, 200), "status": extraction.status,
                            "message_id": message.id, "subject": safe(message.subject, 200),
                            "text": safe(extraction.text, 8000), "reason": safe(extraction.reason, 500)})
                        if extraction.status == "dangerous":
                            self.store.outbox("danger:inspect:" + item["reference"] + ":" + message.id, time.time(),
                                "URGENT attachment danger detected for " + item["reference"] + ". Further attachment processing stopped.", "danger")
                            return result
        return result

    def _owner_transition(self, item):
        # Fence already queued work independently of opaque provider IDs and
        # wall-clock processing time. Jobs are retained, so rowids stay stable.
        item["owner_controlled"] = True
        item["control_grant"] = list(self.store.active_grant) if self.store.active_grant else None
        item["owner_queue"] = max(item.get("owner_queue", 0), self.store.rows("SELECT COALESCE(MAX(rowid),0) AS position FROM jobs")[0]["position"])
        item["owner_received"] = max(item.get("owner_received", -1),
                                     item.get("activity_received", item.get("received", 0)))

    def migrate_owner_fences(self):
        """One bounded compatibility pass before intake; no queue/data deletion.

        The old format recorded correction only in a fixed author-written marker.
        It is recognised here solely to conservatively protect legacy state,
        never as evidence that incoming content supersedes an obligation.
        """
        with self.store.transaction() as db:
            position = db.execute("SELECT COALESCE(MAX(rowid),0) FROM jobs").fetchone()[0]
            for row in db.execute("SELECT * FROM items").fetchall():
                item = json.loads(row["data"])
                if "owner_queue" in item and "owner_received" in item:
                    continue
                explicit_effect = db.execute("SELECT 1 FROM effects WHERE reference=? AND id NOT LIKE 'auto:%' LIMIT 1", (row["reference"],)).fetchone()
                controlled = (item.get("owner_controlled") or item["classification"] in {"done", "waiting"}
                    or item.get("snooze_until") is not None or item.get("reminder_at") is not None
                    or ("context_source" not in item and item.get("reason") == "Explicit owner correction.") or explicit_effect)
                if not controlled:
                    continue
                item.update(owner_controlled=True, owner_queue=max(position, item.get("owner_queue", 0)),
                    owner_received=max(item.get("owner_received", -1), item.get("last_sent", 0),
                                       item.get("activity_received", item.get("received", 0))))
                db.execute("UPDATE items SET version=version+1,data=? WHERE seq=?", (dump(item), row["seq"]))
                db.execute("UPDATE effects SET status='cancelled' WHERE reference=? AND id LIKE 'auto:%' AND status='pending'", (row["reference"],))

    def correct(self, access, reference, payload):
        self.guard(access)
        exact(payload, {"version", "classification", "always"}, {"rule"})
        if (not isinstance(payload["classification"], str) or payload["classification"] not in CLASSIFICATIONS or type(payload["always"]) is not bool
                or type(payload["version"]) is not int or (payload["always"] and "rule" not in payload)
                or (not payload["always"] and "rule" in payload)):
            raise invalid("Correction requires classification, version and explicit rule approval")
        rule = self.rule_store.validate(payload["rule"]) if payload["always"] else None
        saved = None
        with self.store.operation():
            item = self.store.item(reference)
            if item["version"] != payload["version"]:
                raise Error("version_conflict", "Item changed; reload and review.", 409, current=self.public_item(item))
            item.update(classification=payload["classification"], reason="Explicit owner correction.",
                        reminder_at=None, snooze_until=None, changed=time.time())
            self._owner_transition(item)
            account = self.store.account(item["mailbox_id"])
            with self.store.transaction() as db:
                if rule:
                    saved = self.rule_store._save(db, rule, None, None, None)
                    item["rule_id"] = saved["id"]
                self.store.put_item(account, item["thread_id"], item, db=db)
            suggestion = mutable("Review this sender", "sender", item["sender"] or "unknown", payload["classification"])
            suggestion["mailbox_id"] = item["mailbox_id"]
            return {"item": self.public_item(self.store.item(item["reference"])),
                    "suggested_rule": suggestion, "applied_rule": saved}

    def _effect(self, item, archived, db):
        key = item["reference"] + ":" + str(item["version"] + 1) + (":archive" if archived else ":restore")
        db.execute("INSERT OR IGNORE INTO effects(id,mailbox_id,thread_id,reference,desired) VALUES(?,?,?,?,?)",
                   (key, item["mailbox_id"], item["thread_id"], item["reference"], dump({"archived": archived, "grant": self.store.active_grant})))

    def retry_effects(self):
        for effect in self.store.rows("SELECT * FROM effects WHERE status='pending' ORDER BY rowid"):
            current = self.current_settings()
            account = self.store.account(effect["mailbox_id"])
            intent = json.loads(effect["desired"])
            if (intent.get("grant") and tuple(intent["grant"]) != self.store.active_grant
                    or not intent.get("grant") and current.grant_revision):
                self.store.execute("UPDATE effects SET status='cancelled' WHERE id=?", (effect["id"],))
                continue
            item = self.store.item(effect["reference"])
            automatic = effect["id"].startswith("auto:")
            message_id = intent.get("message_id")
            if automatic and (not message_id or item.get("latest_message") != message_id
                    or item["classification"] != "fyi" or item["attachment_status"] not in {"ok", "none"}):
                # Legacy thread-wide automatic intents and superseded decisions
                # cannot be replayed against a newer obligation.
                self.store.execute("UPDATE effects SET status='cancelled' WHERE id=?", (effect["id"],))
                continue
            provider = self.provider(account)
            current = self.current_settings()
            if (intent.get("grant") and tuple(intent["grant"]) != self.store.active_grant
                    or not intent.get("grant") and current.grant_revision):
                self.store.execute("UPDATE effects SET status='cancelled' WHERE id=?", (effect["id"],))
                continue
            if automatic:
                provider.archive_message(message_id)
                archived = not provider.thread_state(effect["thread_id"])["inbox"]
            else:
                provider.archive(effect["thread_id"], intent["archived"])
                archived = intent["archived"]
            item = self.store.item(effect["reference"])
            with self.store.transaction() as db:
                if not automatic or (item.get("latest_message") == message_id and item["classification"] == "fyi"):
                    item["archived"] = archived
                    self.store.put_item(account, item["thread_id"], item, db=db)
                db.execute("UPDATE effects SET status='done' WHERE id=?", (effect["id"],))

    def action(self, access, reference, action, *, at=None):
        self.guard(access)
        if action not in {"done", "archive", "restore", "snooze", "waiting", "remind"}:
            raise invalid("Unsupported action")
        now = time.time()
        if action in {"snooze", "remind"} or (action == "waiting" and at is not None):
            if type(at) not in {int, float} or not now < at < now + 366 * 86400:
                raise invalid("Provide an explicit future time within one year, including timezone")
        with self.store.operation():
            self.migrate_owner_fences()
            item = self.store.item(reference)
            if action == "done" and item["classification"] == "done":
                previous = dict(item)
                self._owner_transition(item)
                item.pop("activity_review", None)
                if item != previous:
                    self.store.put_item(self.store.account(item["mailbox_id"]), item["thread_id"], item)
                self.retry_effects()
                return self.public_item(self.store.item(item["reference"]))
            item["changed"] = now
            self._owner_transition(item)
            if action == "done":
                item.update(classification="done", reminder_at=None, snooze_until=None, reason="Owner marked done.")
                item.pop("activity_review", None)
            elif action == "snooze":
                item["snooze_until"] = at
            elif action == "waiting":
                item.update(classification="waiting", reminder_at=at, snooze_until=None, reason="Owner is waiting for a reply; follow-up date is explicit.")
            elif action == "remind":
                item["reminder_at"] = at
            if action in {"snooze", "waiting", "remind"}:
                item["schedule_grant"] = list(self.store.active_grant)
            account = self.store.account(item["mailbox_id"])
            with self.store.transaction() as db:
                if action == "done":
                    db.execute("UPDATE outbox SET state='cancelled',error=NULL WHERE category='reminder' AND id LIKE ? AND state IN ('pending','retry','blocked')",
                               ("reminder:" + item["reference"] + ":%",))
                if action in {"done", "archive", "restore", "snooze"}:
                    self._effect(item, action != "restore", db)
                self.store.put_item(account, item["thread_id"], item, db=db)
            self.retry_effects()
            return self.public_item(self.store.item(item["reference"]))

    def historical(self, access, mailbox_id, after, before, limit=100):
        self.guard(access)
        if (type(after) not in {int, float} or type(before) not in {int, float}
                or not 0 <= after < before <= time.time() + 1 or before - after > 31 * 86400
                or type(limit) is not int or not 1 <= limit <= 500):
            raise invalid("Historical scope needs ordered dates within 31 days and limit 1–500")
        with self.store.operation():
            account = self.store.account(mailbox_id)
            ids = self.provider(account).historical(after, before, limit)
            self.store.queue(mailbox_id, ids, account["checkpoint"])
        return {"queued": len(ids), "scope": {"after": after, "before": before, "limit": limit}, "synthetic": False}

    def recover_history(self, access, mailbox_id, after, limit=100):
        self.guard(access)
        if (type(after) not in {int, float} or not 0 <= after < time.time()
                or time.time() - after > 31 * 86400 or type(limit) is not int or not 1 <= limit <= 500):
            raise invalid("Explicit history recovery needs a start within 31 days and limit 1–500")
        with self.store.operation():
            account = self.store.account(mailbox_id)
            provider = self.provider(account)
            profile = provider.profile()
            if profile["address"].casefold() != account["address"].casefold():
                raise Error("account_mismatch", "OAuth grant belongs to a different mailbox.", 403)
            before = time.time() + 1
            ids = provider.historical(after, before, limit)
            self.store.queue(mailbox_id, ids, profile["checkpoint"])
            self.store.execute("UPDATE accounts SET last_error=NULL WHERE id=?", (mailbox_id,))
        return {"queued": len(ids), "scope": {"after": after, "before": before, "limit": limit},
                "old_checkpoint": account["checkpoint"], "new_checkpoint": profile["checkpoint"],
                "notice": "Explicit cutover approved: only the selected Inbox date scope is recovered; older/out-of-Inbox messages are not replayed."}

    def consent(self, access, value):
        self.guard(access)
        if value not in {CONSENT, "off"}:
            raise invalid(DISCLOSURE)
        self.store.set_meta("model_consent", value if value == CONSENT else "")
        return {"model_consent": value, "disclosure": DISCLOSURE}
