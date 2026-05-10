"""
Thread pool manager for concurrent WeChat account operations.
Uses multiprocessing for CPU-bound tasks to avoid GIL issues,
and ThreadPoolExecutor for I/O-bound tasks.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Any, Optional
from queue import Queue, Empty

from src.database import DatabaseManager
from src.api import get_updates, DEFAULT_BASE_URL
from src.message_handler import process_received_messages
from src.cursor_manager import CursorManager


class AccountWorker:
    """Worker for a single WeChat account that polls for messages."""
    
    def __init__(self, account_id: str, token: str, base_url: str,
                 db: DatabaseManager, cursor_manager: CursorManager):
        self.account_id = account_id
        self.token = token
        self.base_url = base_url
        self.db = db
        self.cursor_manager = cursor_manager
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self, poll_interval: float = 5.0) -> None:
        """Start polling for messages in a background thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(poll_interval,),
            daemon=True,
            name=f"wechat-worker-{self.account_id}"
        )
        self._thread.start()
    
    def stop(self) -> None:
        """Stop polling."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
    
    def _poll_loop(self, poll_interval: float) -> None:
        """Main polling loop."""
        while self._running:
            try:
                cursor = self.cursor_manager.load_cursor(self.account_id)
                response = get_updates(self.token, self.base_url, cursor)
                
                messages = response.get("msgs", [])
                new_cursor = response.get("get_updates_buf", cursor)
                
                if messages:
                    process_received_messages(self.db, self.account_id, messages)
                    self.cursor_manager.save_cursor(self.account_id, new_cursor)
                
            except Exception as e:
                print(f"[Worker {self.account_id}] Error: {e}")
            
            time.sleep(poll_interval)


class ThreadPoolManager:
    """Manages thread pool for concurrent WeChat operations."""
    
    def __init__(self, db: DatabaseManager, cursor_manager: CursorManager,
                 max_workers: int = 10):
        self.db = db
        self.cursor_manager = cursor_manager
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._workers: dict[str, AccountWorker] = {}
        self._lock = threading.Lock()
        self._poll_interval = 5.0
    
    def start_all_accounts(self, poll_interval: float = 5.0) -> int:
        """Start workers for all logged-in accounts."""
        self._poll_interval = poll_interval
        accounts = self.db.list_accounts()
        started = 0
        
        for account in accounts:
            if account.get("login_status") == "logged_in" and account.get("token"):
                account_id = account["account_id"]
                with self._lock:
                    if account_id not in self._workers:
                        worker = AccountWorker(
                            account_id=account_id,
                            token=account["token"],
                            base_url=account.get("base_url", DEFAULT_BASE_URL),
                            db=self.db,
                            cursor_manager=self.cursor_manager,
                        )
                        worker.start(poll_interval)
                        self._workers[account_id] = worker
                        started += 1
        
        return started
    
    def stop_all(self) -> None:
        """Stop all workers."""
        with self._lock:
            for worker in self._workers.values():
                worker.stop()
            self._workers.clear()
        
        self._executor.shutdown(wait=True)
    
    def submit_task(self, func: Callable, *args, **kwargs) -> Future:
        """Submit a task to the thread pool."""
        return self._executor.submit(func, *args, **kwargs)
    
    def refresh_workers(self) -> None:
        """Refresh workers based on current account list."""
        accounts = self.db.list_accounts()
        active_ids = set()
        
        for account in accounts:
            if account.get("login_status") == "logged_in" and account.get("token"):
                account_id = account["account_id"]
                active_ids.add(account_id)
                
                with self._lock:
                    if account_id not in self._workers:
                        worker = AccountWorker(
                            account_id=account_id,
                            token=account["token"],
                            base_url=account.get("base_url", DEFAULT_BASE_URL),
                            db=self.db,
                            cursor_manager=self.cursor_manager,
                        )
                        worker.start(self._poll_interval)
                        self._workers[account_id] = worker
        
        with self._lock:
            to_remove = [aid for aid in self._workers if aid not in active_ids]
            for aid in to_remove:
                self._workers[aid].stop()
                del self._workers[aid]
