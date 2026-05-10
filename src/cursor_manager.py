"""
Cursor persistence for message polling.
Manages per-account polling cursors to avoid re-delivering old messages.
"""
import json
import threading
from typing import Optional
from pathlib import Path


class CursorManager:
    """Manages polling cursors for each account."""
    
    def __init__(self, cursor_dir: Optional[str] = None):
        if cursor_dir is None:
            cursor_dir = Path.home() / ".mcp-wechat-clawbot" / "cursors"
        
        self._cursor_dir = Path(cursor_dir)
        self._cursor_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
    
    def _cursor_path(self, account_id: str) -> Path:
        return self._cursor_dir / f"{account_id}.cursor.json"
    
    def load_cursor(self, account_id: str) -> str:
        """Load cursor for an account."""
        cursor_path = self._cursor_path(account_id)
        if not cursor_path.exists():
            return ""
        
        try:
            with open(cursor_path, 'r') as f:
                data = json.load(f)
            return data.get("cursor", "")
        except (json.JSONDecodeError, IOError):
            return ""
    
    def save_cursor(self, account_id: str, cursor: str) -> None:
        """Save cursor for an account."""
        with self._lock:
            cursor_path = self._cursor_path(account_id)
            with open(cursor_path, 'w') as f:
                json.dump({"cursor": cursor}, f)
    
    def reset_cursor(self, account_id: str) -> None:
        """Reset cursor for an account."""
        with self._lock:
            cursor_path = self._cursor_path(account_id)
            if cursor_path.exists():
                cursor_path.unlink()
