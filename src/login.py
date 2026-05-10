"""
QR code login handler for WeChat accounts.
Displays QR code in terminal for scanning and handles the login flow.
"""
import sys
import time
import uuid
from typing import Optional

try:
    from qrcode_terminal import generate as qr_generate
except ImportError:
    qr_generate = None

from src.api import fetch_qr_code, poll_qr_status, DEFAULT_BASE_URL
from src.database import DatabaseManager


def display_qr_code(qr_url: str):
    """Display QR code in terminal."""
    if qr_generate:
        qr_generate(qr_url, small=True)
    else:
        print(f"\n{'='*60}")
        print(f"Please scan the following URL with WeChat:")
        print(f"{qr_url}")
        print(f"{'='*60}\n")


def handle_qr_login(db: DatabaseManager, base_url: str = DEFAULT_BASE_URL) -> dict:
    """
    Handle QR code login flow.
    Returns account data dict on success.
    """
    print("🔐 WeChat MCP — QR Login\n")
    print("Fetching QR code...")
    
    qr_data = fetch_qr_code(base_url)
    qrcode_token = qr_data.get("qrcode", "")
    qrcode_url = qr_data.get("qrcode_img_content", "")
    
    print("\nScan this QR code with WeChat:\n")
    display_qr_code(qrcode_url)
    print("\nWaiting for scan...")
    
    attempts = 0
    qr_refresh_count = 0
    current_qrcode_token = qrcode_token
    current_qrcode_url = qrcode_url
    
    while attempts < 90:
        time.sleep(2)
        attempts += 1
        
        try:
            status = poll_qr_status(current_qrcode_token, base_url)
        except Exception as e:
            print(f"\rPoll error: {e}")
            continue
        
        status_val = status.get("status", "")
        
        if status_val == "scaned":
            sys.stdout.write("\r✓ Scanned! Waiting for confirmation...")
            sys.stdout.flush()
        elif status_val == "confirmed":
            token = status.get("bot_token")
            if not token:
                raise Exception("No token in confirmed response")
            
            new_base_url = status.get("baseurl", base_url)
            user_id = status.get("ilink_user_id") or status.get("ilink_bot_id")
            account_id = (status.get("ilink_bot_id", "")
                         .replace("@", "-")
                         .replace(".", "-") or 
                         f"{uuid.uuid4().hex[:12]}-im-bot")
            
            db.add_account(account_id, user_id or "", token, new_base_url)
            
            print(f"\n🎉 Logged in! Account: {account_id}")
            print(f"   UserId: {user_id or '(unknown)'}")
            print("\nYou can now start the MCP server.")
            
            return {
                "account_id": account_id,
                "user_id": user_id,
                "token": token,
                "base_url": new_base_url,
            }
        elif status_val == "expired":
            qr_refresh_count += 1
            if qr_refresh_count > 3:
                print("\n❌ QR code expired 3 times. Please run again.")
                sys.exit(1)
            
            print(f"\n⏳ QR code expired, refreshing... ({qr_refresh_count}/3)")
            refreshed = fetch_qr_code(base_url)
            current_qrcode_token = refreshed.get("qrcode", "")
            current_qrcode_url = refreshed.get("qrcode_img_content", "")
            print("\nNew QR code — scan with WeChat:\n")
            display_qr_code(current_qrcode_url)
    
    print("\n❌ Timeout waiting for scan.")
    sys.exit(1)


def check_existing_login(db: DatabaseManager) -> Optional[dict]:
    """Check if there are any logged-in accounts."""
    accounts = db.list_accounts()
    for account in accounts:
        if account.get("login_status") == "logged_in" and account.get("token"):
            return account
    return None


def login_or_use_existing(db: DatabaseManager, base_url: str = DEFAULT_BASE_URL) -> dict:
    """
    Try to use existing login if available, otherwise perform QR login.
    Returns account data dict.
    """
    existing = check_existing_login(db)
    if existing:
        print(f"✅ Using existing login for account: {existing['account_id']}")
        return existing
    
    return handle_qr_login(db, base_url)


if __name__ == "__main__":
    db = DatabaseManager()
    handle_qr_login(db)
