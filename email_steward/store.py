"""Private SQLite metadata; full bodies and attachment bytes never enter this store."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import stat
import unicodedata
import uuid

from .errors import Error


def private_dir(path):
    path = Path(path)
    if path.is_symlink():
        raise PermissionError("state directory must not be a symlink")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise PermissionError("state directory has foreign owner")
    path.chmod(0o700)
    return path


def prefix(address):
    letters = [c for c in unicodedata.normalize("NFKC", address.split("@", 1)[0]).casefold() if c.isalpha()]
    return (letters[0] + letters[-1]) if letters else "xx"


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Store:
    def __init__(self, root):
        self.root = private_dir(root)
        self.path = self.root / "state.sqlite3"
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        with self.transaction() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,address TEXT UNIQUE NOT NULL,
              display_name TEXT NOT NULL,grant_id TEXT UNIQUE NOT NULL,checkpoint TEXT NOT NULL,
              baseline REAL NOT NULL,last_poll REAL,last_error TEXT);
            CREATE TABLE IF NOT EXISTS rules(id TEXT PRIMARY KEY,version INTEGER NOT NULL,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS packs(pack TEXT NOT NULL,scope TEXT NOT NULL,rule_ids TEXT NOT NULL,PRIMARY KEY(pack,scope));
            CREATE TABLE IF NOT EXISTS items(seq INTEGER PRIMARY KEY AUTOINCREMENT,reference TEXT UNIQUE,
              mailbox_id TEXT NOT NULL,thread_id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,
              UNIQUE(mailbox_id,thread_id));
            CREATE TABLE IF NOT EXISTS messages(mailbox_id TEXT NOT NULL,id TEXT NOT NULL,thread_id TEXT NOT NULL,
              processed REAL NOT NULL,PRIMARY KEY(mailbox_id,id));
            CREATE TABLE IF NOT EXISTS jobs(mailbox_id TEXT NOT NULL,id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',
              attempts INTEGER NOT NULL DEFAULT 0,next_try REAL NOT NULL DEFAULT 0,error TEXT,PRIMARY KEY(mailbox_id,id));
            CREATE TABLE IF NOT EXISTS effects(id TEXT PRIMARY KEY,mailbox_id TEXT NOT NULL,thread_id TEXT NOT NULL,
              reference TEXT NOT NULL,desired TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending');
            CREATE TABLE IF NOT EXISTS digests(id TEXT PRIMARY KEY,slot TEXT UNIQUE NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS aliases(digest TEXT NOT NULL,alias TEXT NOT NULL,reference TEXT NOT NULL,
              PRIMARY KEY(digest,alias));
            CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,created REAL NOT NULL,text TEXT NOT NULL,
              category TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
              next_try REAL NOT NULL DEFAULT 0,error TEXT);
            ''')
            columns = {r[1] for r in db.execute("PRAGMA table_info(outbox)")}
            for name, definition in (("grant_generation", "INTEGER"), ("grant_fingerprint", "TEXT")):
                if name not in columns:
                    db.execute(f"ALTER TABLE outbox ADD COLUMN {name} {definition}")
        self.active_grant = None
        self.trusted_links = ()
        self._permissions()

    def _permissions(self):
        for path in self.root.iterdir():
            if path.is_file() and not path.is_symlink():
                path.chmod(0o600)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def operation(self, *, blocking=True):
        fd = os.open(self.root / "operations.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False
                return
            yield True
        finally:
            os.close(fd)

    def rows(self, query, params=()):
        with self.transaction() as db:
            return [dict(r) for r in db.execute(query, params)]

    def execute(self, query, params=()):
        with self.transaction() as db:
            return db.execute(query, params).rowcount

    def meta(self, key, default=None):
        rows = self.rows("SELECT value FROM meta WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set_meta(self, key, value):
        self.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, dump(value)))

    def accounts(self):
        return self.rows("SELECT * FROM accounts ORDER BY id")

    def account(self, ident):
        found = self.rows("SELECT * FROM accounts WHERE id=?", (ident,))
        if not found:
            raise Error("not_found", "Mailbox not found.", 404)
        return found[0]

    @staticmethod
    def decode_item(row):
        return {**json.loads(row["data"]), "reference": row["reference"], "mailbox_id": row["mailbox_id"],
                "thread_id": row["thread_id"], "version": row["version"]}

    def items(self):
        return [self.decode_item(r) for r in self.rows("SELECT * FROM items ORDER BY seq")]

    def resolve(self, reference):
        if not isinstance(reference, str) or len(reference) > 100:
            raise Error("not_found", "Reference not found.", 404)
        if ":" in reference:
            digest, alias = reference.rsplit(":", 1)
            hits = self.rows("SELECT reference FROM aliases WHERE digest=? AND alias=?", (digest, alias.upper()))
        elif reference.upper().startswith("A") and reference[1:].isdigit():
            hits = self.rows("SELECT reference FROM aliases WHERE alias=?", (reference.upper(),))
            if len(hits) > 1:
                raise Error("ambiguous_alias", "Alias is ambiguous; qualify it with its digest id.", 409)
        else:
            hits = self.rows("SELECT reference FROM items WHERE reference=?", (reference,))
        if not hits:
            raise Error("not_found", "Reference not found.", 404)
        return hits[0]["reference"]

    def item(self, reference):
        ref = self.resolve(reference)
        return self.decode_item(self.rows("SELECT * FROM items WHERE reference=?", (ref,))[0])

    def put_item(self, account, thread_id, data, *, db=None):
        if db is None:
            with self.transaction() as connection:
                return self.put_item(account, thread_id, data, db=connection)
        found = db.execute("SELECT * FROM items WHERE mailbox_id=? AND thread_id=?", (account["id"], thread_id)).fetchone()
        payload = {k: v for k, v in data.items() if k not in {"reference", "version", "mailbox_id", "thread_id"}}
        if found:
            db.execute("UPDATE items SET version=version+1,data=? WHERE seq=?", (dump(payload), found["seq"]))
            return found["reference"]
        cursor = db.execute("INSERT INTO items(mailbox_id,thread_id,version,data) VALUES(?,?,1,?)", (account["id"], thread_id, dump(payload)))
        reference = prefix(account["address"]) + str(cursor.lastrowid)
        db.execute("UPDATE items SET reference=? WHERE seq=?", (reference, cursor.lastrowid))
        return reference

    def queue(self, mailbox, ids, checkpoint):
        with self.transaction() as db:
            for ident in ids:
                if not db.execute("SELECT 1 FROM messages WHERE mailbox_id=? AND id=?", (mailbox, ident)).fetchone():
                    db.execute("INSERT OR IGNORE INTO jobs(mailbox_id,id) VALUES(?,?)", (mailbox, ident))
            db.execute("UPDATE accounts SET checkpoint=? WHERE id=?", (str(checkpoint), mailbox))

    def outbox(self, ident, now, text, category="brief", *, db=None, grant=None):
        if db is None:
            with self.transaction() as connection:
                return self.outbox(ident, now, text, category, db=connection, grant=grant)
        from .outbound import chunks
        from .presentation import gmail_link
        generation, fingerprint = grant or self.active_grant or (None, None)
        try:
            links = tuple(gmail_link(r["address"], r["thread_id"]) for r in db.execute(
                "SELECT accounts.address,items.thread_id FROM items JOIN accounts ON items.mailbox_id=accounts.id"))
            parts = chunks(text, links)
            state, error = "pending", None
        except ValueError:
            parts, state, error = ["Email Steward: oversized native payload held; inspect locally."], "blocked", "Payload cannot fit without loss"
        for index, part in enumerate(parts):
            key = ident if index == 0 else ident + ":part:" + str(index + 1)
            db.execute("INSERT OR IGNORE INTO outbox(id,created,text,category,state,error,grant_generation,grant_fingerprint) VALUES(?,?,?,?,?,?,?,?)",
                (key, now, part, category, state, error, generation, fingerprint))
