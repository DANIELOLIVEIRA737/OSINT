"""Local SQLite projects, evidence, reports and monitor schedules."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,target TEXT NOT NULL,mode TEXT NOT NULL,created_at TEXT NOT NULL,body TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',bookmarks TEXT NOT NULL DEFAULT '[]');
                CREATE INDEX IF NOT EXISTS reports_project ON reports(project_id,created_at);
                CREATE TABLE IF NOT EXISTS monitors(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,target TEXT NOT NULL,deep INTEGER NOT NULL,hours INTEGER NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,next_run REAL NOT NULL,last_run TEXT,last_error TEXT,last_report_id TEXT);
            """
            )

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def projects(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT p.*, (SELECT count(*) FROM reports r WHERE r.project_id=p.id) AS report_count FROM projects p ORDER BY created_at DESC"
                )
            ]

    def create(self, name):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError("Nome de projeto inválido (1–120 caracteres).")
        pid = uuid.uuid4().hex
        with self.connect() as db:
            db.execute(
                "INSERT INTO projects(id,name,created_at) VALUES(?,?,?)",
                (pid, name.strip(), now()),
            )
        return self.project(pid)

    def project(self, pid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
            if row is None:
                raise KeyError("Projeto não encontrado.")
            result = dict(row)
            result["reports"] = [
                dict(r)
                for r in db.execute(
                    "SELECT id,target,mode,created_at,notes,bookmarks FROM reports WHERE project_id=? ORDER BY created_at DESC",
                    (pid,),
                )
            ]
            for report in result["reports"]:
                report["bookmarks"] = json.loads(report["bookmarks"])
            result["monitors"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM monitors WHERE project_id=? ORDER BY next_run",
                    (pid,),
                )
            ]
            return result

    def edit(self, pid, notes):
        self.project(pid)
        if not isinstance(notes, str) or len(notes) > 50000:
            raise ValueError("Notas demasiado longas.")
        with self.connect() as db:
            db.execute("UPDATE projects SET notes=? WHERE id=?", (notes, pid))
        return self.project(pid)

    def delete(self, pid):
        self.project(pid)
        with self.connect() as db:
            db.execute("DELETE FROM projects WHERE id=?", (pid,))

    def save_report(self, pid, report):
        self.project(pid)
        if (
            not isinstance(report, dict)
            or not isinstance(report.get("target"), str)
            or not isinstance(report.get("results"), dict)
            or len(json.dumps(report)) > 8000000
        ):
            raise ValueError("Relatório inválido.")
        rid = uuid.uuid4().hex
        body = dict(report)
        body.pop("saved_id", None)
        body.pop("project_id", None)
        if "comparison" not in body:
            previous = self.previous(pid, body["target"], body.get("mode", "standard"))
            if previous:
                from intelligence import compare

                body["comparison"] = compare(previous, body)
        with self.connect() as db:
            db.execute(
                "INSERT INTO reports(id,project_id,target,mode,created_at,body) VALUES(?,?,?,?,?,?)",
                (
                    rid,
                    pid,
                    body["target"],
                    body.get("mode", "standard"),
                    now(),
                    json.dumps(body),
                ),
            )
        return self.report(rid)

    def report(self, rid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
            if row is None:
                raise KeyError("Relatório não encontrado.")
            return json.loads(row["body"]) | {
                "saved_id": rid,
                "project_id": row["project_id"],
                "analyst_notes": row["notes"],
                "bookmarks": json.loads(row["bookmarks"]),
            }

    def annotate(self, rid, notes, bookmarks):
        report = self.report(rid)
        if (
            not isinstance(notes, str)
            or len(notes) > 50000
            or not isinstance(bookmarks, list)
            or any(
                not isinstance(key, str) or key not in report["results"]
                for key in bookmarks
            )
        ):
            raise ValueError("Notas ou evidências inválidas.")
        with self.connect() as db:
            db.execute(
                "UPDATE reports SET notes=?,bookmarks=? WHERE id=?",
                (notes, json.dumps(sorted(set(bookmarks))), rid),
            )
        return self.report(rid)

    def previous(self, pid, target, mode):
        with self.connect() as db:
            row = db.execute(
                "SELECT id FROM reports WHERE project_id=? AND target=? AND mode=? ORDER BY created_at DESC LIMIT 1",
                (pid, target, mode),
            ).fetchone()
        return self.report(row["id"]) if row else None

    def monitor(self, pid, target, deep, hours):
        import time

        self.project(pid)
        if (
            type(hours) is not int
            or hours not in (1, 6, 12, 24, 168)
            or type(deep) is not bool
        ):
            raise ValueError("Intervalo de monitorização inválido.")
        with self.connect() as db:
            if db.execute("SELECT count(*) FROM monitors").fetchone()[0] >= 30:
                raise ValueError("Limite de 30 monitorizações atingido.")
            mid = uuid.uuid4().hex
            db.execute(
                "INSERT INTO monitors(id,project_id,target,deep,hours,next_run) VALUES(?,?,?,?,?,?)",
                (mid, pid, target, int(deep), hours, time.time() + hours * 3600),
            )
        return mid

    def set_monitor(self, mid, enabled):
        if type(enabled) is not bool:
            raise ValueError("Estado de monitorização inválido.")
        with self.connect() as db:
            cur = db.execute(
                "UPDATE monitors SET enabled=? WHERE id=?", (int(enabled), mid)
            )
            if not cur.rowcount:
                raise KeyError("Monitorização não encontrada.")

    def get_monitor(self, mid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM monitors WHERE id=?", (mid,)).fetchone()
        if row is None:
            raise KeyError("Monitorização não encontrada.")
        return dict(row)

    def due(self):
        import time

        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM monitors WHERE enabled=1 AND next_run<=? ORDER BY next_run",
                    (time.time(),),
                )
            ]

    def finish_monitor(self, mid, rid, error):
        import time

        with self.connect() as db:
            db.execute(
                "UPDATE monitors SET last_run=?,last_error=?,last_report_id=?,next_run=?+hours*3600 WHERE id=?",
                (now(), error, rid, time.time(), mid),
            )


class InstanceLock:
    """OS-managed lock: automatically released if the process crashes."""

    def __init__(self, directory):
        self.path = Path(directory) / "instance.lock"
        self.handle = None

    def __enter__(self):
        import os

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0, 2)
                if self.handle.tell() == 0:
                    self.handle.write(b"0")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise RuntimeError(
                "O Atlas já está a utilizar esta pasta de dados. Aguarde ou abra a instância existente."
            )
        return self

    def __exit__(self, *args):
        import os

        if self.handle:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
