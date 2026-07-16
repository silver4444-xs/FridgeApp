"""基于 SQLite 的持久化 Store，用于跨会话用户偏好。

实现 langgraph.store.BaseStore 接口的 get/put/search 子集，
与 InMemoryStore 的 tools.py 使用模式兼容。

与 AsyncSqliteSaver (langgraph-checkpoint-sqlite) 共享同一个 SQLite 数据库文件，
使 checkpointer 和 store 数据共存。
"""

import json
import sqlite3
import threading
from typing import Any, Optional


class SQLiteStore:
    """SQLite 支持的 BaseStore 兼容实现，用于用户偏好。

    用法:
        store = SQLiteStore("checkpoints.db")
        store.put(("preferences",), "user_abc", {"忌口": ["辣"], "菜系": "川菜"})
        prefs = store.get(("preferences",), "user_abc")
    """

    def __init__(self, db_path: str = "checkpoints.db"):
        self._db_path = db_path
        self._local = threading.local()
        self._init_table()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_table(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS store (
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (namespace, key)
            )
        """)
        conn.commit()

    def _encode(self, namespace: tuple) -> str:
        return "|".join(str(n) for n in namespace)

    def get(self, namespace: tuple, key: str) -> Optional[dict]:
        conn = self._get_conn()
        ns = self._encode(namespace)
        row = conn.execute(
            "SELECT value FROM store WHERE namespace = ? AND key = ?",
            (ns, key),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["value"])

    def put(self, namespace: tuple, key: str, value: dict):
        conn = self._get_conn()
        ns = self._encode(namespace)
        conn.execute(
            "INSERT OR REPLACE INTO store (namespace, key, value) VALUES (?, ?, ?)",
            (ns, key, json.dumps(value, ensure_ascii=False)),
        )
        conn.commit()

    def search(self, namespace: tuple) -> list:
        conn = self._get_conn()
        ns = self._encode(namespace)
        rows = conn.execute(
            "SELECT namespace, key, value FROM store WHERE namespace = ?",
            (ns,),
        ).fetchall()
        return [
            {"namespace": tuple(r["namespace"].split("|")), "key": r["key"], "value": json.loads(r["value"])}
            for r in rows
        ]

    def delete(self, namespace: tuple, key: str):
        conn = self._get_conn()
        ns = self._encode(namespace)
        conn.execute(
            "DELETE FROM store WHERE namespace = ? AND key = ?",
            (ns, key),
        )
        conn.commit()
