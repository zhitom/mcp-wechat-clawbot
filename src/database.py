"""
SQLite database module for storing accounts, chat messages, and login info.
Uses WAL mode for better concurrent read/write performance and avoids GIL issues
by using connection-per-thread pattern.
"""
import sqlite3
import os
import threading
from pathlib import Path
from typing import Optional
from datetime import datetime


DB_SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    token TEXT NOT NULL,
    base_url TEXT NOT NULL DEFAULT 'https://ilinkai.weixin.qq.com',
    login_status TEXT NOT NULL DEFAULT 'logged_in',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    message_id TEXT,
    from_user_id TEXT NOT NULL,
    to_user_id TEXT NOT NULL,
    message_type INTEGER NOT NULL,
    message_state INTEGER,
    text_content TEXT,
    context_token TEXT,
    raw_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_text TEXT,
    context_token TEXT,
    msg_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, user_id),
    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS login_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    qrcode_token TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_account ON chat_messages(account_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_from_user ON chat_messages(from_user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_contacts_account_user ON contacts(account_id, user_id);
"""


class _LocalThreadDB(threading.local):
    """Thread-local storage for database connections."""
    def __init__(self):
        super().__init__()
        self.connection: Optional[sqlite3.Connection] = None


_local_db = _LocalThreadDB()


class DatabaseManager:
    """Manages SQLite database with thread-safe connection handling."""
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_dir = Path.home() / ".mcp-wechat-clawbot"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "clawbot.db")
        
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = self.get_connection()
        conn.executescript(SCHEMA_SQL)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.commit()
    
    def get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if _local_db.connection is None:
            _local_db.connection = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                timeout=30.0
            )
            _local_db.connection.row_factory = sqlite3.Row
            _local_db.connection.execute("PRAGMA journal_mode=WAL")
            _local_db.connection.execute("PRAGMA busy_timeout=5000")
            _local_db.connection.execute("PRAGMA foreign_keys=ON")
        return _local_db.connection
    
    def add_account(self, account_id: str, user_id: str, token: str, 
                    base_url: str = "https://ilinkai.weixin.qq.com") -> bool:
        """Add or update an account. Returns True if added/updated."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.execute(
                """INSERT INTO accounts (account_id, user_id, token, base_url, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(account_id) DO UPDATE SET
                       token=excluded.token,
                       base_url=excluded.base_url,
                       user_id=excluded.user_id,
                       login_status='logged_in',
                       updated_at=excluded.updated_at""",
                (account_id, user_id, token, base_url, datetime.now().isoformat())
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def get_account(self, account_id: str) -> Optional[dict]:
        """Get account by ID."""
        conn = self.get_connection()
        row = conn.execute(
            "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone()
        return dict(row) if row else None
    
    def get_account_by_user_id(self, user_id: str) -> Optional[dict]:
        """Get account by user ID."""
        conn = self.get_connection()
        row = conn.execute(
            "SELECT * FROM accounts WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    
    def list_accounts(self) -> list[dict]:
        """List all accounts."""
        conn = self.get_connection()
        rows = conn.execute(
            "SELECT * FROM accounts ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    
    def delete_account(self, account_id: str) -> bool:
        """Delete an account and all associated data."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.execute(
                "DELETE FROM accounts WHERE account_id = ?", (account_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def clear_all_accounts(self) -> int:
        """Clear all accounts and associated data. Returns count of deleted accounts."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.execute("DELETE FROM accounts")
            conn.commit()
            return cursor.rowcount
    
    def update_login_status(self, account_id: str, status: str) -> bool:
        """Update account login status."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.execute(
                "UPDATE accounts SET login_status = ?, updated_at = ? WHERE account_id = ?",
                (status, datetime.now().isoformat(), account_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def add_chat_message(self, account_id: str, from_user_id: str, to_user_id: str,
                        message_type: int, text_content: Optional[str] = None,
                        message_id: Optional[str] = None, 
                        message_state: Optional[int] = None,
                        context_token: Optional[str] = None,
                        raw_message: Optional[str] = None) -> int:
        """Add a chat message. Returns the message ID."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.execute(
                """INSERT INTO chat_messages 
                   (account_id, message_id, from_user_id, to_user_id, message_type, 
                    message_state, text_content, context_token, raw_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (account_id, message_id, from_user_id, to_user_id, message_type,
                 message_state, text_content, context_token, raw_message)
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_chat_history(self, account_id: Optional[str] = None, 
                        from_user_id: Optional[str] = None,
                        limit: int = 50, offset: int = 0) -> list[dict]:
        """Get chat message history with filters."""
        conn = self.get_connection()
        query = "SELECT * FROM chat_messages WHERE 1=1"
        params: list = []
        
        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        if from_user_id:
            query += " AND from_user_id = ?"
            params.append(from_user_id)
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    
    def update_contact(self, account_id: str, user_id: str, last_text: Optional[str] = None,
                      context_token: Optional[str] = None) -> bool:
        """Update or insert a contact."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.execute(
                """INSERT INTO contacts (account_id, user_id, last_seen, last_text, context_token, msg_count, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)
                   ON CONFLICT(account_id, user_id) DO UPDATE SET
                       last_seen=excluded.last_seen,
                       last_text=COALESCE(excluded.last_text, contacts.last_text),
                       context_token=COALESCE(excluded.context_token, contacts.context_token),
                       msg_count=contacts.msg_count + 1,
                       updated_at=excluded.updated_at""",
                (account_id, user_id, datetime.now().isoformat(), last_text, context_token, datetime.now().isoformat())
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def get_contacts(self, account_id: Optional[str] = None) -> list[dict]:
        """Get contacts list."""
        conn = self.get_connection()
        if account_id:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE account_id = ? ORDER BY updated_at DESC",
                (account_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM contacts ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]
    
    def add_login_session(self, account_id: str, user_id: str, 
                         qrcode_token: Optional[str] = None) -> int:
        """Add a login session record."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.execute(
                """INSERT INTO login_sessions (account_id, user_id, qrcode_token, status)
                   VALUES (?, ?, ?, 'pending')""",
                (account_id, user_id, qrcode_token)
            )
            conn.commit()
            return cursor.lastrowid
    
    def update_login_session(self, session_id: int, status: str) -> bool:
        """Update login session status."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.execute(
                """UPDATE login_sessions SET status = ?, 
                   completed_at = CASE WHEN ? = 'completed' THEN ? ELSE completed_at END
                   WHERE id = ?""",
                (status, status, datetime.now().isoformat(), session_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def close_all(self):
        """Close all thread-local connections."""
        if _local_db.connection:
            _local_db.connection.close()
            _local_db.connection = None
