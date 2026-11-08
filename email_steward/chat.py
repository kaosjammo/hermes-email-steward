"""One native plaintext command path. Identity is never accepted in tool args."""
from datetime import datetime, timedelta, timezone
import json
import time
import uuid

from .errors import Error, invalid
from .judgement import DISCLOSURE
from .security import discord_access

HELP = """Email Steward · owner-private commands
list | inspect REF [text|attachments] | done/archive/restore REF
snooze/remind REF ISO8601-with-offset | waiting REF [ISO8601-with-offset]
rules | rule-save JSON | rule-update ID JSON | rule-toggle ID JSON
packs | pack-enable ID JSON | preview JSON | correct REF JSON
brief | health | outbox | delivery-confirm ID | delivery-retry ID
historical MAILBOX AFTER_ISO BEFORE_ISO LIMIT
recover-history MAILBOX AFTER_ISO LIMIT (explicit bounded recovery and history cutover)
schedule JSON (briefs/timezone/quiet_start/quiet_end/quiet_bypass)
consent [model-routing-v2|off]
Aliases: D<digest-id>:A1, or A1 only if unambiguous across all saved briefs.
"""


def explicit_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.timestamp()
    except (ValueError, TypeError):
        example = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="minutes")
        raise invalid("Use a date and time with a UTC offset, for example " + example +
                      ". Choose your intended future time; this example does not schedule anything.") from None


class Chat:
    def __init__(self, service_factory, worker_factory, config_writer=None):
        self.service_factory, self.worker_factory, self.config_writer = service_factory, worker_factory, config_writer

    def run(self, raw, *, source=None):
        try:
            s = self.service_factory()
            access = discord_access(s.settings, source)
            s.guard(access)
            command, _, tail = raw.strip().partition(" ")
            if not command or command == "help":
                return {"help": HELP, "disclosure": DISCLOSURE}
            if command == "list":
                return {"items": s.items(access)}
            if command == "rules":
                return {"rules": s.rules(access)}
            if command == "packs":
                return {"packs": s.packs(access)}
            if command == "rule-save":
                return {"rule": s.save_rule(access, self._json(tail))}
            if command in {"rule-update", "rule-toggle", "pack-enable", "correct"}:
                ident, _, payload = tail.partition(" ")
                body = self._json(payload)
                if command == "rule-update":
                    return {"rule": s.save_rule(access, body, ident)}
                if command == "rule-toggle":
                    return {"rule": s.toggle_rule(access, ident, body)}
                if command == "pack-enable":
                    return {"rules": s.enable_pack(access, ident, body)}
                return s.correct(access, ident, body)
            if command == "preview":
                return s.preview(access, self._json(tail))
            if command == "consent":
                return s.consent(access, tail) if tail else {"disclosure": DISCLOSURE}
            if command == "inspect":
                args = tail.split()
                if not 1 <= len(args) <= 2 or (len(args) == 2 and args[1] not in {"text", "attachments"}):
                    raise invalid("inspect REF [text|attachments]")
                result = s.inspect(access, args[0], text=args[-1] == "text", attachments=args[-1] == "attachments")
                if args[-1] == "attachments":
                    with s.store.operation():
                        self.worker_factory(s).flush()
                return result
            if command in {"done", "archive", "restore", "snooze", "remind", "waiting"}:
                args = tail.split()
                if not 1 <= len(args) <= 2:
                    raise invalid("Supply a reference and optional explicit time")
                return {"item": s.action(access, args[0], command, at=explicit_time(args[1]) if len(args) == 2 else None)}
            if command in {"health", "brief"}:
                worker = self.worker_factory(s)
                if command == "health":
                    import time
                    return {"health": worker.health(time.time()), "heartbeat": s.store.meta("heartbeat")}
                with s.store.operation():
                    digest = worker.brief()
                    worker.flush()
                return {"digest": digest}
            if command == "outbox":
                rows = s.store.rows("SELECT id,created,category,state,attempts,error,grant_generation FROM outbox WHERE state NOT IN ('sent','accepted') ORDER BY rowid")
                return {"outbox": [{**row, "origin": s.store.meta("gateway_grant:" + str(row["grant_generation"]))} for row in rows]}
            if command in {"delivery-confirm", "delivery-retry"}:
                states = ("uncertain", "blocked", "handed_to_cron", "handed_off") if command == "delivery-retry" else ("uncertain", "handed_to_cron", "handed_off")
                if not tail or not s.store.rows("SELECT 1 FROM outbox WHERE id=? AND state IN (" + ",".join("?" for _ in states) + ")", (tail, *states)):
                    raise invalid("Choose an uncertain or handed-off (or blocked for retry) outbox id; retry may duplicate a delivery")
                row = s.store.rows("SELECT * FROM outbox WHERE id=?", (tail,))[0]
                if command == "delivery-retry" and row["category"] == "command":
                    raise invalid("Inspection/command bodies are not cached; explicitly repeat the command after considering duplicate risk")
                if command == "delivery-retry" and row["category"] == "reminder" and s.store.item(tail.split(":", 2)[1])["classification"] == "done":
                    raise invalid("Done resolved this obligation; an obsolete reminder cannot be retried")
                if (row["grant_generation"], row["grant_fingerprint"]) != s.store.active_grant:
                    raise Error("grant_revoked", "Historical delivery belongs to a revoked or unprovable grant; it cannot be retried or approved under this destination.", 403)
                s.store.execute("UPDATE outbox SET state=?,next_try=0,error=NULL WHERE id=?",
                    ("sent" if command == "delivery-confirm" else "pending", tail))
                return {"outbox_id": tail, "state": "sent" if command == "delivery-confirm" else "pending", "duplicate_risk_acknowledged": command == "delivery-retry"}
            if command == "historical":
                args = tail.split()
                if len(args) != 4:
                    raise invalid("historical MAILBOX AFTER_ISO BEFORE_ISO LIMIT")
                return s.historical(access, args[0], explicit_time(args[1]), explicit_time(args[2]), int(args[3]))
            if command == "recover-history":
                args = tail.split()
                if len(args) != 3:
                    raise invalid("recover-history MAILBOX AFTER_ISO LIMIT explicitly approves bounded recovery/current-history cutover")
                return s.recover_history(access, args[0], explicit_time(args[1]), int(args[2]))
            if command == "schedule":
                payload = self._json(tail)
                from dataclasses import replace
                if not isinstance(payload, dict) or not payload or set(payload) - {"briefs", "timezone", "quiet_start", "quiet_end", "quiet_bypass"}:
                    raise invalid("Schedule allows briefs, timezone and quiet hours/bypass only")
                replace(s.settings, **payload)
                if self.config_writer is None:
                    raise Error("configuration_unavailable", "Host configuration writer unavailable.", 503)
                for key, value in payload.items():
                    self.config_writer(key, value)
                return {"schedule": payload}
            raise invalid("Unknown command. Use help.")
        except Error as exc:
            return exc.body
        except (ValueError, TypeError):
            return invalid("Invalid arguments or JSON").body
        except Exception:
            return Error("service_unavailable", "Operation failed; pending work is retained. Check owner health/outbox.", 503).body

    @staticmethod
    def _json(text):
        if len(text) > 100000:
            raise invalid("JSON input exceeds limit")
        try:
            return json.loads(text)
        except ValueError:
            raise invalid("Invalid JSON") from None

    def command(self, raw_args, *, source=None, **context):
        from .outbound import chunks
        from .gateways import fingerprint
        from .replies import command_reply, error_reply
        try:
            service = self.service_factory()
            settings = service.current_settings()
            service.guard(discord_access(settings, source))
            original = (fingerprint(settings), settings.grant_revision, service.store.active_grant)
            result = self.run(raw_args, source=source)
            text = command_reply(raw_args, result, service.store, settings.timezone)
            digest = result.get("digest")
            if digest:
                rows = service.store.rows("SELECT id,text FROM outbox WHERE id LIKE ? ORDER BY rowid",
                                          ("brief:" + digest + ":%",))
                text = "\n\n".join(row["text"] for row in rows)
            parts = chunks(text, service.store.trusted_links)
            if len(parts) > 1024:
                return "Reply exceeds the bounded inspection budget. Request text or attachments separately."
            with service.store.operation():
                fresh = service.current_settings()
                service.guard(discord_access(fresh, source))
                if (fingerprint(fresh), fresh.grant_revision, service.store.active_grant) != original:
                    raise Error("grant_revoked", "Grant changed while processing the command; reply withheld.", 403)
                if digest:
                    # The command contract hands text to core. It supplies no delivery receipt.
                    # Keep that distinction, and do not also push the same brief through cron.
                    for row in rows:
                        service.store.execute("UPDATE outbox SET state='handed_off',error=? WHERE id=?",
                            ("Returned to the originating host command; delivery unconfirmed", row["id"]))
            return "\n\n".join(parts)
        except Error as error:
            return chunks(error_reply(error.body["error"]))[0]

    def tool(self, args, **kwargs):
        if not isinstance(args, dict) or set(args) != {"command"} or not isinstance(args["command"], str):
            return json.dumps(invalid("Only command text is accepted; identity is transport-owned").body)
        if args["command"].strip() == "help":
            return json.dumps({"help": HELP, "disclosure": DISCLOSURE, "native_source_required": True})
        # The supported model bridge omits off-wire receiving adapter/account authority.
        # Never reconstruct it from ambient session variables or borrow a live chat.
        return json.dumps(Error("forbidden", "Use the actual-source /email-steward command or explicitly granted Desktop/CLI; the reduced model bridge cannot prove native authority.", 403).body)
