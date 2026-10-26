import json
import sqlite3
import time


class MetricsLogger:
    def __init__(self, db_path="metrics.sqlite"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS tool_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT,
            tool_name TEXT,
            success INTEGER,
            duration_ms INTEGER,
            args TEXT,
            error TEXT,
            timestamp TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS workflow_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT,
            steps INTEGER,
            tools_used TEXT,
            stuck_counter INTEGER,
            last_message TEXT,
            timestamp TEXT
        )
        """)

        conn.commit()
        conn.close()

    def log_tool(self, thread_id, tool_name, success, duration_ms, args=None, error=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
        INSERT INTO tool_metrics
        (thread_id, tool_name, success, duration_ms, args, error, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            thread_id,
            tool_name,
            int(success),
            duration_ms,
            args,
            error,
            time.strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()

    def log_workflow(self, thread_id, state):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        last_message = None
        messages = state.get("messages")

        if messages:
            raw = getattr(messages[-1], "content", None)

            if isinstance(raw, str):
                last_message = raw
            else:
                last_message = json.dumps(raw, ensure_ascii=False)

        c.execute("""
        INSERT INTO workflow_metrics
        (thread_id, steps, tools_used, stuck_counter, last_message, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            thread_id,
            state.get("step_count", 0),
            ",".join(
                trace.get("tool", "unknown")
                for trace in state.get("tools_trace", [])
            ),
            state.get("stuck_counter", 0),
            last_message,
            time.strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()
