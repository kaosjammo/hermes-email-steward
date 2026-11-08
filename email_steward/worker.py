"""Durable intake, metadata transitions and an honest private-delivery outbox."""
from dataclasses import replace
import json
import time
import uuid

from .errors import Error
from .judgement import assess
from .presentation import gmail_link, redact
from .replies import LABELS, decision_reason, next_step
from .scheduling import due_slots, quiet
from .store import dump, private_dir
from .gmail import bounded_content


class Worker:
    def __init__(self, service, delivery, *, extractor=None, crash=None):
        self.service, self.store, self.delivery = service, service.store, delivery
        self.extractor = extractor
        self.crash = crash or (lambda point: None)

    def _settings(self):
        settings = self.service.current_settings()
        consent = self.store.meta("model_consent", settings.model_consent)
        return replace(settings, model_consent=consent)

    def tick(self, now=None):
        now = time.time() if now is None else now
        self._settings().require_private()
        self._settings().require_schedule()
        started = time.monotonic()
        observed = lambda: now + time.monotonic() - started
        with self.store.operation() as acquired:
            if not acquired:
                return
            self.service.migrate_owner_fences()
            errors = []
            try:
                self.service.retry_effects()
                self._due(now)
            except Exception:
                errors.append("Provider lifecycle changes are pending retry")
            for account in self.store.accounts():
                try:
                    self._poll(account, observed())
                    self.store.execute("UPDATE accounts SET last_poll=?,last_error=NULL WHERE id=?", (observed(), account["id"]))
                except Exception:
                    self.store.execute("UPDATE accounts SET last_error=? WHERE id=?", ("Gmail intake or conversation reconciliation failed; retry pending", account["id"]))
                    errors.append("Mailbox " + account["id"] + " is unhealthy")
            for job in self.store.rows("SELECT * FROM jobs WHERE status='pending' AND next_try<=? ORDER BY rowid LIMIT 100", (now,)):
                try:
                    self._process(job, observed())
                except Exception:
                    self.store.execute("UPDATE jobs SET attempts=attempts+1,next_try=?,error=? WHERE mailbox_id=? AND id=?",
                        (now + min(30 * 2 ** min(job["attempts"], 5), 900), "Processing or provider mutation failed; retry pending", job["mailbox_id"], job["id"]))
                    errors.append("Message processing pending retry")
            for account in self.store.accounts():
                try:
                    self._sync(account, observed())
                except Exception:
                    self.store.execute("UPDATE accounts SET last_error=? WHERE id=?", ("Conversation reconciliation failed; retry pending", account["id"]))
                    errors.append("Conversation reconciliation pending")
            now = observed()
            self.store.set_meta("worker_health", {"at": now, "errors": errors})
            self.crash("before_schedule")
            previous = self.store.meta("schedule_cursor", now - 60)
            for stamp, slot in due_slots(self._settings(), previous, now):
                self.brief(now, key=slot, scheduled_at=stamp)
            self.store.set_meta("schedule_cursor", now)
            self.flush(now)
            self.store.set_meta("heartbeat", now)

    def _poll(self, account, now):
        provider = self.service.provider(account)
        profile = provider.profile()
        if profile["address"].casefold() != account["address"].casefold():
            raise Error("account_mismatch", "Mailbox grant changed accounts; processing refused.", 403)
        ids, checkpoint = provider.changes(account["checkpoint"])
        self.crash("before_queue")
        self.store.queue(account["id"], ids, checkpoint)
        self.crash("after_queue")

    def _attachments(self, message, job, now):
        from .extraction import extract
        extractor = self.extractor or extract
        status, texts = ("unreadable" if message.content_hold else "none"), []
        started = time.monotonic()
        rank = {"none": 0, "ok": 1, "unsupported": 2, "unreadable": 3, "dangerous": 4}
        for attachment in message.attachments[:20]:
            if attachment.size > 16 * 1024 * 1024:
                status = "unreadable"
                continue
            extraction = extractor(attachment.load(), attachment.filename, attachment.content_type,
                                   scratch_root=private_dir(self.store.root / "scratch"))
            if rank[extraction.status] > rank[status]:
                status = extraction.status
            if extraction.status == "dangerous":
                event_now = now + time.monotonic() - started
                self.store.outbox(f"danger:{job['mailbox_id']}:{job['id']}", event_now,
                    "URGENT suspected dangerous attachment. Batch stopped. Mailbox " + job["mailbox_id"] +
                    "; subject: " + redact(message.subject, 200) + ". " + redact(extraction.reason, 400) +
                    ". Do not open it. Detection does not guarantee all malicious files are recognised.", "danger")
                # Immediate attempt, before any other processing or model call. Destination remains fixed.
                self.flush(event_now)
                break
            if extraction.status == "ok":
                texts.append(extraction.text)
        if len(message.attachments) > 20:
            status = "unreadable" if status != "dangerous" else status
        content, clipped = bounded_content([message.body, *texts])
        if clipped and status != "dangerous":
            status = "unreadable"
        return status, content

    def _process(self, job, now):
        started = time.monotonic()
        account = self.store.account(job["mailbox_id"])
        provider = self.service.provider(account)
        message = provider.fetch(job["id"])
        if message.excluded or message.sent or not message.inbox:
            self.store.execute("UPDATE jobs SET status='excluded',error=NULL WHERE mailbox_id=? AND id=?", (account["id"], job["id"]))
            return
        if self.store.rows("SELECT 1 FROM messages WHERE mailbox_id=? AND id=?", (account["id"], message.id)):
            self.store.execute("UPDATE jobs SET status='done',error=NULL WHERE mailbox_id=? AND id=?", (account["id"], job["id"]))
            return
        status, content = self._attachments(message, job, now)
        sample = dict(mailbox_id=account["id"], sender=message.sender, subject=message.subject,
                      body=content)
        settings = self._settings()
        decision_grant = self.store.active_grant
        decision = assess(sample, status, self.service.rule_store.list(), settings, self.service.model)
        prior = next((i for i in self.store.items() if i["mailbox_id"] == account["id"] and i["thread_id"] == message.thread_id), None)
        now += time.monotonic() - started
        item = {**decision, "sender": redact(message.sender, 320), "subject": redact(message.subject, 1000),
                "attachment_status": status, "archived": not message.inbox, "latest_message": message.id,
                "received": message.received, "changed": now, "snooze_until": None, "reminder_at": None,
                "last_sent": (prior or {}).get("last_sent", 0), "link": gmail_link(account["address"], message.thread_id),
                "late": now - message.received > 300}
        if prior and prior.get("reminder_at") and item["classification"] == "waiting":
            item["reminder_at"] = prior["reminder_at"]
        position = self.store.rows("SELECT rowid AS position FROM jobs WHERE mailbox_id=? AND id=?",
                                   (account["id"], job["id"]))[0]["position"]
        item, context_changed = self._merge_context(prior, item, position)
        if item.get("activity_review"):
            decision["archive"] = False
        # Label mutation is idempotent. Mark processed only after label succeeds.
        self.service.current_settings()
        provider.mark_triaged(message.id)
        self.crash("after_triaged")
        # Resolve rule presentation before taking the write transaction. RuleStore.list
        # opens its own connection; calling it inside this transaction self-deadlocks.
        rule_name = next((r["name"] for r in self.service.rule_store.list()
                          if r["id"] == decision.get("rule_id")), None)
        with self.store.transaction() as db:
            ref = self.store.put_item(account, message.thread_id, item, db=db)
            db.execute("INSERT OR IGNORE INTO messages VALUES(?,?,?,?)", (account["id"], message.id, message.thread_id, now))
            db.execute("UPDATE jobs SET status='done',error=NULL WHERE mailbox_id=? AND id=?", (account["id"], job["id"]))
            if context_changed and decision["archive"]:
                db.execute("INSERT OR IGNORE INTO effects(id,mailbox_id,thread_id,reference,desired) VALUES(?,?,?,?,?)",
                    ("auto:" + account["id"] + ":" + message.id, account["id"], message.thread_id, ref,
                     dump({"archived": True, "message_id": message.id, "grant": decision_grant})))
            if context_changed and decision["urgent"]:
                self.store.outbox("urgent:" + account["id"] + ":" + message.id, now,
                    "URGENT · " + ref + "\n" + redact(message.subject, 200) + "\n" + redact(decision["summary"], 400) +
                    "\nWhy now: " + redact(decision_reason(decision, rule_name), 500) +
                    ("\nDeadline: " + redact(decision["deadline"], 100) if decision.get("deadline") else "") +
                    ("\nDelayed alert: assessment exceeded the five-minute target." if item["late"] else "") +
                    "\n" + next_step(settings, ref) + "\n" + item["link"],
                    decision["urgent_category"], db=db, grant=decision_grant)
        self.crash("after_processed")
        self.service.retry_effects()
        if context_changed and decision["urgent"]:
            self.flush(now)

    @staticmethod
    def _merge_context(prior, incoming, position):
        """Keep unresolved substance separate from the latest assessed activity.

        Gmail internalDate orders context; equal-date open contexts are retained
        conservatively. Owner queue fences and Sent dates survive restarts.
        No message body or per-thread assessment history is stored here.
        """
        if not prior:
            return {**incoming, "activity_received": incoming["received"],
                    "activity_message": incoming["latest_message"], "activity_subject": incoming["subject"]}, True
        received = incoming["received"]
        older = (received <= prior["received"] and prior["classification"] in {"needs_action", "needs_review", "waiting"})
        fenced = (position <= prior.get("owner_queue", 0)
                  or received < prior.get("owner_received", prior["received"] if prior["classification"] == "done" else -1)
                  or received <= prior.get("last_sent", -1))
        informational = not incoming.get("context_source") and (
            prior["classification"] != "fyi" or prior.get("snooze_until") or prior.get("reminder_at"))
        retain = older or fenced or informational
        merged = dict(prior if retain else incoming)
        for key in ("owner_queue", "owner_received", "owner_controlled", "activity_review"):
            if key in prior:
                merged[key] = prior[key]
        activity = prior.get("activity_received", prior["received"])
        is_new_activity = received > activity
        merged.update(activity_received=max(activity, received),
                      activity_message=incoming["latest_message"] if is_new_activity else prior.get("activity_message", prior["latest_message"]),
                      activity_subject=incoming["subject"] if is_new_activity else prior.get("activity_subject", prior["subject"]))
        if retain and is_new_activity and not older and not fenced and incoming["classification"] != "fyi":
            ranks = {"none": 1, "ok": 1, "unsupported": 2, "unreadable": 3, "dangerous": 4}
            previous = merged.get("activity_review", {})
            if ranks[incoming["attachment_status"]] >= ranks.get(previous.get("attachment_status"), 0):
                merged["activity_review"] = {"message_id": incoming["latest_message"], "received": received,
                    **{k: incoming[k] for k in ("subject", "summary", "reason", "classification", "attachment_status", "holds")}}
                if "model_routing" in incoming:
                    merged["activity_review"]["model_routing"] = incoming["model_routing"]
        review = merged.get("activity_review")
        if review:
            ranks = {"none": 0, "ok": 1, "unsupported": 2, "unreadable": 3, "dangerous": 4}
            if ranks[review["attachment_status"]] > ranks[merged["attachment_status"]]:
                merged["attachment_status"] = review["attachment_status"]
            merged["holds"] = list(dict.fromkeys(merged["holds"] + review.get("holds", [])))
        if retain and is_new_activity:
            merged["changed"] = incoming["changed"]
        return merged, not retain

    def _sync(self, account, now):
        provider = self.service.provider(account)
        items = [i for i in self.store.items() if i["mailbox_id"] == account["id"]]
        for item in sorted(items, key=lambda i: i.get("synced_at", 0))[:10]:
            state = provider.thread_state(item["thread_id"])
            changed = False
            archived = not state["inbox"]
            if archived != item["archived"]:
                item["archived"], changed = archived, True
                if archived and item["classification"] in {"needs_action", "needs_review", "waiting"}:
                    item["reason"] = "Archived manually in Gmail; obligation remains outstanding. Ask owner in next brief."
            if state["sent_at"] > item.get("last_sent", 0):
                item["last_sent"], changed = state["sent_at"], True
                if state["sent_at"] >= item.get("received", 0) and item["classification"] in {"needs_action", "needs_review"}:
                    item.update(classification="waiting", reason="Your Gmail reply was detected. Waiting for response; choose a follow-up date.")
            item["synced_at"] = now
            if changed:
                item["changed"] = now
                self.store.put_item(account, item["thread_id"], item)
            else:
                payload = {k: v for k, v in item.items() if k not in {"reference", "version", "mailbox_id", "thread_id"}}
                self.store.execute("UPDATE items SET data=? WHERE reference=?", (dump(payload), item["reference"]))

    def _due(self, now):
        for item in self.store.items():
            bound = item.get("schedule_grant")
            if ((bound and tuple(bound) != self.store.active_grant)
                    or not bound and self._settings().grant_revision):
                # Preserve historical schedules without silently granting a new route
                # permission to deliver old owner-approved reminders/snoozes.
                continue
            changed, restore = False, False
            if item.get("snooze_until") and item["snooze_until"] <= now:
                item.update(snooze_until=None, changed=now)
                changed = restore = True
            if item.get("reminder_at") and item["reminder_at"] <= now:
                due = item["reminder_at"]
                self.store.outbox(f"reminder:{item['reference']}:{due}", now,
                    "Reminder · " + item["reference"] + "\n" + redact(item["subject"], 200) + "\n" + redact(item["summary"], 400) +
                    "\n" + next_step(self._settings(), item["reference"]) + "\n" + item["link"], "reminder")
                item.update(reminder_at=None, changed=now)
                changed = True
            if changed:
                account = self.store.account(item["mailbox_id"])
                with self.store.transaction() as db:
                    if restore:
                        self.service._effect(item, False, db)
                    self.store.put_item(account, item["thread_id"], item, db=db)
        self.service.retry_effects()

    def health(self, now):
        accounts = self.store.accounts()
        errors = []
        if not self.service.settings.timezone:
            errors.append("Profile timezone is unconfigured; scheduling is refused")
        if not accounts:
            errors.append("No connected mailboxes")
        for a in accounts:
            if a["last_error"] or a["last_poll"] is None or now - a["last_poll"] > 300:
                errors.append("Mailbox " + a["id"] + " intake/reconciliation unhealthy or late")
        heartbeat = self.store.meta("heartbeat")
        if heartbeat is not None and now - heartbeat > 300:
            errors.append("Worker heartbeat is late")
        if self.store.rows("SELECT 1 FROM outbox WHERE state='pending' AND created<? LIMIT 1", (now - 300,)):
            errors.append("Queued delivery is late")
        if any(now - i.get("synced_at", i.get("changed", now)) > 300 for i in self.store.items()):
            errors.append("Conversation reconciliation is late")
        for table, condition, label in (("jobs", "status='pending'", "processing pending"),
                                        ("effects", "status='pending'", "provider changes pending"),
                                        ("outbox", "state IN ('blocked','retry','uncertain','sending')", "delivery blocked/retry/uncertainty")):
            if self.store.rows(f"SELECT 1 FROM {table} WHERE {condition} LIMIT 1"):
                errors.append(label)
        return errors

    def brief(self, now=None, *, key=None, scheduled_at=None):
        now = time.time() if now is None else now
        key = key or "manual:" + uuid.uuid4().hex
        existing = self.store.rows("SELECT id FROM digests WHERE slot=?", (key,))
        if existing:
            return existing[0]["id"]
        health = self.health(now)
        last = self.store.meta("last_brief", 0)
        items = [i for i in self.store.items() if not i.get("snooze_until") and (
            i["classification"] in {"needs_action", "needs_review", "waiting"} or i.get("changed", 0) > last)]
        def section(item):
            if item["classification"] in {"needs_action", "needs_review", "waiting"}:
                return 0, "Outstanding actions and questions"
            return (1, "FYI (new or changed)") if item["classification"] == "fyi" else (2, "Other updates")
        items.sort(key=lambda item: section(item)[0])
        digest = "D" + uuid.uuid4().hex[:12]
        lines = ["Email Steward brief " + digest]
        if health:
            lines.append("UNHEALTHY/PARTIAL: " + "; ".join(health) + ". This is not an all-clear.")
        if scheduled_at and now - scheduled_at > 300:
            lines.append("Scheduled brief is late by more than five minutes.")
        if not items and not health:
            lines.append("All clear: intake is healthy and no new or outstanding items.")
        accounts = {a["id"]: a for a in self.store.accounts()}
        rule_names = {r["id"]: r["name"] for r in self.service.rule_store.list()}
        blocks = ["\n".join(lines)]
        guidance = next_step(self._settings())
        with self.store.transaction() as db:
            db.execute("INSERT INTO digests VALUES(?,?,?)", (digest, key, now))
            current_section = None
            for number, item in enumerate(items, 1):
                heading = section(item)[1]
                if heading != current_section:
                    blocks.append(heading)
                    current_section = heading
                alias = "A" + str(number)
                db.execute("INSERT INTO aliases VALUES(?,?,?)", (digest, alias, item["reference"]))
                summary_limit, reason_limit = (200, 250) if item["classification"] == "fyi" else (400, 500)
                lines = [f"{alias} · {item['reference']} · {redact(accounts[item['mailbox_id']]['address'], 320)} · {LABELS.get(item['classification'], item['classification'])}",
                    redact(item["sender"], 200) + " · " + redact(item["subject"], 200), redact(item["summary"], summary_limit),
                    "Why: " + redact(decision_reason(item, rule_names.get(item.get("rule_id"))), reason_limit),
                    ("Deadline: " + redact(item["deadline"], 100) if item.get("deadline") else ""),
                    ("Attachment warning: " + item["attachment_status"] if item["attachment_status"] not in {"ok", "none"} else ""),
                    ("Late: assessment exceeded five-minute target." if item.get("late") else ""), item["link"]]
                if item.get("activity_message", item["latest_message"]) != item["latest_message"]:
                    lines.append("Latest assessed activity: " + redact(item.get("activity_subject", "Follow-up"), 200))
                review = item.get("activity_review")
                if review:
                    lines.extend(["Additional activity review (" + LABELS.get(review["classification"], review["classification"]) + "): " + redact(review["subject"], 200),
                        redact(review["summary"], 240) + "; " + redact(review["reason"], 500),
                        "Activity attachment status: " + review["attachment_status"]])
                blocks.append("\n".join(line for line in lines if line))
            blocks.append(guidance)
            # Logical item blocks stay intact where possible; the outbox owns byte
            # budgets, continuation identity and each independently authorised row.
            self.store.outbox("brief:" + digest + ":0", now, "\n\n".join(blocks), "brief", db=db)
        self.store.set_meta("last_brief", now)
        return digest

    def flush(self, now=None):
        if self.delivery is None:
            # Production transport is Hermes cron. Intake/commands only queue;
            # the explicit cron operation durably hands eligible rows to stdout.
            return
        now = time.time() if now is None else now
        settings = self._settings()
        settings.require_private()
        # A process died after intent was durably marked, before outcome: do not resend blindly.
        self.store.execute("UPDATE outbox SET state='uncertain',error='Delivery outcome unknown after interruption; owner reconciliation required' WHERE state='sending'")
        for row in self.store.rows("SELECT * FROM outbox WHERE state IN ('pending','retry') AND next_try<=? ORDER BY rowid LIMIT 100", (now,)):
            try:
                settings = self._settings()
                settings.require_private()
            except Error:
                # No send was invoked: leave the remaining row pending rather
                # than inventing a sent/uncertain outcome after revocation.
                return
            if quiet(settings, now, row["category"]):
                continue
            generation, fingerprint = self.store.active_grant
            if row["grant_generation"] != generation or row["grant_fingerprint"] != fingerprint:
                self.store.execute("UPDATE outbox SET state='blocked',error='Selected private grant revoked; historical row not rerouted' WHERE id=?", (row["id"],))
                continue
            self.store.execute("UPDATE outbox SET state='sending',attempts=attempts+1 WHERE id=?", (row["id"],))
            self.crash("before_delivery")
            try:
                outcome = self.delivery.send(settings, row["text"], row["id"])
            except Exception:
                outcome = "uncertain"
            self.crash("after_delivery")
            if outcome not in {"sent", "accepted", "blocked", "retry", "uncertain"}:
                outcome = "uncertain"
            self.store.execute("UPDATE outbox SET state=?,next_try=?,error=? WHERE id=?",
                (outcome, now + min(30 * 2 ** min(row["attempts"], 5), 900),
                 None if outcome in {"sent", "accepted"} else "Delivery blocked or uncertain; inspect owner outbox", row["id"]))
