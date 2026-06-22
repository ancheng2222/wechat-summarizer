"""
消息存储模块 —— SQLite 读写，支持去重、按日期查询、按发送人过滤
"""
import sqlite3
import hashlib
import os
from datetime import datetime, date
from typing import Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "messages.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """建表（如果不存在）"""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            msg_time TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(group_name, msg_time, sender, content_hash)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_msg_time ON messages(msg_time)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sender ON messages(sender)
    """)
    conn.commit()
    conn.close()


def _hash_content(content: str) -> str:
    """对消息内容前 50 字符做 MD5"""
    return hashlib.md5(content[:50].encode("utf-8")).hexdigest()


def save_messages(group_name: str, messages: list[dict]) -> int:
    """
    批量保存消息，自动去重。
    每条消息格式: {"time": "2026-06-20 14:30:00", "sender": "张三", "content": "..."}
    返回实际新增数量。
    """
    conn = _get_conn()
    count = 0
    for msg in messages:
        content_hash = _hash_content(msg.get("content", ""))
        try:
            conn.execute(
                "INSERT OR IGNORE INTO messages (group_name, sender, content, msg_time, content_hash) "
                "VALUES (?, ?, ?, ?, ?)",
                (group_name, msg["sender"], msg["content"], msg["time"], content_hash),
            )
            if conn.changes > 0:
                count += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return count


def get_messages(
    group_name: str,
    target_date: Optional[date] = None,
    senders: Optional[list[str]] = None,
    limit: int = 5000,
) -> list[dict]:
    """
    查询消息。
    - target_date: 不传则查今天
    - senders: 不传则查所有人
    """
    conn = _get_conn()
    conn.row_factory = sqlite3.Row

    if target_date is None:
        target_date = date.today()

    date_str = target_date.strftime("%Y-%m-%d")
    query = "SELECT sender, content, msg_time FROM messages WHERE group_name = ? AND msg_time LIKE ?"
    params: list = [group_name, f"{date_str}%"]

    if senders:
        placeholders = ",".join("?" for _ in senders)
        query += f" AND sender IN ({placeholders})"
        params.extend(senders)

    query += " ORDER BY msg_time ASC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [{"sender": r["sender"], "content": r["content"], "time": r["msg_time"]} for r in rows]


def get_last_msg_time(group_name: str) -> Optional[str]:
    """获取某个群最后一次记录的消息时间，用于增量读取"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT msg_time FROM messages WHERE group_name = ? ORDER BY msg_time DESC LIMIT 1",
        (group_name,),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def get_message_count(group_name: str, target_date: Optional[date] = None) -> int:
    """获取某天消息总数"""
    conn = _get_conn()
    if target_date is None:
        target_date = date.today()
    date_str = target_date.strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE group_name = ? AND msg_time LIKE ?",
        (group_name, f"{date_str}%"),
    ).fetchone()
    conn.close()
    return row[0] if row else 0
