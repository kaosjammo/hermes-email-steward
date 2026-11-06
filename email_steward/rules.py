"""One validator and transactional rule store for every control surface."""
import json
import uuid
from .errors import Error, invalid
from .store import dump

FIELDS = {"name", "enabled", "mailbox_id", "priority", "conditions", "actions"}
CLASSIFICATIONS = {"needs_action", "needs_review", "fyi"}


def exact(value, fields, optional=()):
    if not isinstance(value, dict) or set(value) - set(fields) - set(optional) or set(fields) - set(value):
        raise invalid("Object has missing or unknown fields")


def string(value, field, size):
    if not isinstance(value, str) or not value.strip() or len(value) > size:
        raise invalid("Invalid text field", **{field: f"Use 1–{size} nonblank characters"})
    return value


def validate(value, mailboxes):
    exact(value, FIELDS)
    string(value["name"], "name", 100)
    if type(value["enabled"]) is not bool:
        raise invalid("enabled must be a boolean", enabled="Use true or false")
    if value["mailbox_id"] is not None and (not isinstance(value["mailbox_id"], str) or value["mailbox_id"] not in mailboxes):
        raise invalid("Unknown mailbox scope", mailbox_id="Choose a connected mailbox")
    if type(value["priority"]) is not int or not -1000 <= value["priority"] <= 1000:
        raise invalid("priority must be an integer from −1000 to 1000", priority="Out of range")
    clauses = value["conditions"]
    if not isinstance(clauses, list) or not 1 <= len(clauses) <= 20:
        raise invalid("Use 1–20 AND conditions", conditions="Invalid condition count")
    for clause in clauses:
        exact(clause, {"field", "operator", "value"})
        if (not isinstance(clause["field"], str) or not isinstance(clause["operator"], str)
                or clause["field"] not in {"sender", "subject", "body"} or clause["operator"] not in {"contains", "equals"}):
            raise invalid("Unknown condition field or operator", conditions="Invalid condition")
        string(clause["value"], "conditions", 500)
    exact(value["actions"], {"classification", "archive"})
    actions = value["actions"]
    if (not isinstance(actions["classification"], str) or actions["classification"] not in CLASSIFICATIONS
            or type(actions["archive"]) is not bool):
        raise invalid("Invalid actions", actions="Choose a supported classification and boolean archive")
    if actions["archive"] and actions["classification"] != "fyi":
        raise invalid("Only FYI rules may request automatic archive", actions="Unsafe archive preference")
    return json.loads(dump(value))


def matches(rule, sample):
    return mismatch(rule, sample) is None


def mismatch(rule, sample):
    """One predicate for matching and its read-only preview explanation."""
    if not rule["enabled"]:
        return "This rule is disabled. Enable it to match future mail."
    if rule["mailbox_id"] not in {None, sample["mailbox_id"]}:
        return "The test mailbox is outside this rule's mailbox scope."
    for index, c in enumerate(rule["conditions"], 1):
        actual, expected = sample.get(c["field"], "").casefold(), c["value"].casefold()
        if (expected not in actual) if c["operator"] == "contains" else (expected != actual):
            operation = "contain" if c["operator"] == "contains" else "equal"
            return f"Condition {index} does not match: {c['field']} must {operation} the specified text."
    return None


def mutable(name, field, value, classification, *, priority=0, archive=False):
    return dict(name=name, enabled=True, mailbox_id=None, priority=priority,
                conditions=[dict(field=field, operator="contains", value=value)],
                actions=dict(classification=classification, archive=archive))


PACKS = [
    dict(id="starter-action", name="Direct requests", description="Questions and requests stay visible.", rules=[
        mutable("Please requests", "body", "please", "needs_action", priority=50),
        mutable("Questions", "body", "?", "needs_action", priority=50)]),
    dict(id="starter-info", name="Informational items", description="Suggest FYI for receipts and newsletters; safety and substance holds still apply.", rules=[
        mutable("Receipt", "subject", "receipt", "fyi", archive=True),
        mutable("Confirmation", "subject", "confirmation", "fyi", archive=True),
        mutable("Newsletter", "subject", "newsletter", "fyi", archive=True)]),
    dict(id="starter-review", name="Review uncertainty", description="Uncertain wording stays visible for an owner decision.", rules=[
        mutable("Uncertain", "body", "not sure", "needs_review", priority=75)])]


class RuleStore:
    def __init__(self, store):
        self.store = store

    def validate(self, value):
        return validate(value, {x["id"] for x in self.store.accounts()})

    @staticmethod
    def decode(row):
        return {**json.loads(row["data"]), "id": row["id"], "version": row["version"]}

    def list(self):
        rules = [self.decode(r) for r in self.store.rows("SELECT * FROM rules")]
        return sorted(rules, key=lambda r: (-r["priority"], r["id"]))

    def save(self, value, ident=None, version=None, *, pack_id=None):
        data = self.validate(value)
        with self.store.transaction() as connection:
            return self._save(connection, data, ident, version, pack_id)

    def _save(self, db, data, ident, version, pack_id):
        if ident is None:
            ident = "rule-" + uuid.uuid4().hex
            result = {**data, "pack_id": pack_id, "id": ident, "version": 1}
            db.execute("INSERT INTO rules VALUES(?,?,?)", (ident, 1, dump({**data, "pack_id": pack_id})))
            return result
        row = db.execute("SELECT * FROM rules WHERE id=?", (ident,)).fetchone()
        if not row:
            raise Error("not_found", "Rule not found.", 404)
        current = self.decode(row)
        if type(version) is not int or version != current["version"]:
            raise Error("version_conflict", "Rule changed; reload and review before saving.", 409, current=current)
        result = {**data, "pack_id": current["pack_id"], "id": ident, "version": version + 1}
        db.execute("UPDATE rules SET version=?,data=? WHERE id=?", (version + 1, dump({**data, "pack_id": current["pack_id"]}), ident))
        return result

    def toggle(self, ident, payload):
        exact(payload, {"version", "enabled"})
        if type(payload["enabled"]) is not bool:
            raise invalid("enabled must be a boolean")
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM rules WHERE id=?", (ident,)).fetchone()
            if not row:
                raise Error("not_found", "Rule not found.", 404)
            current = self.decode(row)
            data = {k: current[k] for k in FIELDS}
            data["enabled"] = payload["enabled"]
            return self._save(db, data, ident, payload["version"], current["pack_id"])

    def packs(self):
        installed = self.store.rows("SELECT pack,scope FROM packs")
        return [{**p, "enabled": any(r["pack"] == p["id"] for r in installed),
                 "enabled_scopes": [None if r["scope"] == "" else r["scope"] for r in installed if r["pack"] == p["id"]]} for p in PACKS]

    def enable_pack(self, ident, payload):
        exact(payload, {"mailbox_id"})
        scope = payload["mailbox_id"]
        if scope is not None and (not isinstance(scope, str) or scope not in {a["id"] for a in self.store.accounts()}):
            raise invalid("Unknown mailbox scope")
        pack = next((p for p in PACKS if p["id"] == ident), None)
        if pack is None:
            raise Error("not_found", "Pack not found.", 404)
        values = [self.validate({**r, "mailbox_id": scope}) for r in pack["rules"]]
        with self.store.transaction() as db:
            row = db.execute("SELECT rule_ids FROM packs WHERE pack=? AND scope=?", (ident, scope or "")).fetchone()
            if row:
                return [self.decode(db.execute("SELECT * FROM rules WHERE id=?", (i,)).fetchone()) for i in json.loads(row["rule_ids"])]
            results = [self._save(db, r, None, None, ident) for r in values]
            db.execute("INSERT INTO packs VALUES(?,?,?)", (ident, scope or "", dump([r["id"] for r in results])))
            return results
