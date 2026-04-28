"""SQLite-backed cost ledger."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


SCHEMA_VERSION = 1
DEFAULT_DB = Path("_cache/cost_ledger.db")


class BudgetExhausted(Exception):
    pass


class CostLedger:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as c:
            v = c.execute("PRAGMA user_version").fetchone()[0]
            if v < 1:
                c.executescript("""
                    CREATE TABLE IF NOT EXISTS calls (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts_unix REAL NOT NULL,
                        task TEXT NOT NULL,
                        model TEXT NOT NULL,
                        tokens_in INTEGER NOT NULL,
                        tokens_out INTEGER NOT NULL,
                        cost_usd REAL NOT NULL,
                        latency_ms INTEGER NOT NULL,
                        success INTEGER NOT NULL,
                        trace_id TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_calls_task_ts ON calls(task, ts_unix);
                    CREATE INDEX IF NOT EXISTS idx_calls_model_ts ON calls(model, ts_unix);
                    PRAGMA user_version = 1;
                """)

    def record(
        self,
        *,
        task: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        latency_ms: int,
        success: bool,
        trace_id: str = "",
    ):
        with self._conn() as c:
            c.execute(
                "INSERT INTO calls (ts_unix, task, model, tokens_in, tokens_out, "
                "cost_usd, latency_ms, success, trace_id) VALUES (?,?,?,?,?,?,?,?,?)",
                (time.time(), task, model, tokens_in, tokens_out, cost_usd,
                 latency_ms, int(success), trace_id),
            )

    def summary(
        self,
        *,
        since_unix: float | None = None,
        group_by: str = "task",
    ) -> list[dict]:
        assert group_by in ("task", "model", "day"), f"bad group_by: {group_by}"
        if group_by == "day":
            grouping = "date(ts_unix, 'unixepoch')"
        else:
            grouping = group_by
        where = ""
        params: list = []
        if since_unix is not None:
            where = "WHERE ts_unix >= ?"
            params.append(since_unix)
        with self._conn() as c:
            rows = c.execute(
                f"SELECT {grouping} AS k, COUNT(*) AS calls, "
                f"SUM(tokens_in) AS tin, SUM(tokens_out) AS tout, "
                f"SUM(cost_usd) AS cost, AVG(latency_ms) AS avg_latency_ms, "
                f"SUM(success) AS successes "
                f"FROM calls {where} GROUP BY k ORDER BY cost DESC",
                params,
            ).fetchall()
        cols = ["key", "calls", "tokens_in", "tokens_out", "cost_usd",
                "avg_latency_ms", "successes"]
        return [dict(zip(cols, r)) for r in rows]

    def enforce_budget(self, *, task: str, budget_usd: float, since_unix: float | None = None):
        with self._conn() as c:
            params = [task]
            where = "task = ?"
            if since_unix is not None:
                where += " AND ts_unix >= ?"
                params.append(since_unix)
            spent = c.execute(
                f"SELECT COALESCE(SUM(cost_usd), 0) FROM calls WHERE {where}",
                params,
            ).fetchone()[0]
            if spent >= budget_usd:
                raise BudgetExhausted(
                    f"Task '{task}' spent ${spent:.4f} >= cap ${budget_usd:.2f}"
                )

    def total_spent(self, *, task: str | None = None, since_unix: float | None = None) -> float:
        with self._conn() as c:
            where_parts = []
            params = []
            if task:
                where_parts.append("task = ?")
                params.append(task)
            if since_unix is not None:
                where_parts.append("ts_unix >= ?")
                params.append(since_unix)
            where = "WHERE " + " AND ".join(where_parts) if where_parts else ""
            return c.execute(
                f"SELECT COALESCE(SUM(cost_usd), 0) FROM calls {where}",
                params,
            ).fetchone()[0]
