"""
Account management module for handling multi-account operations.
Provides tools for listing, deleting, and clearing accounts.
"""
from src.database import DatabaseManager


def list_accounts(db: DatabaseManager) -> list:
    """List all accounts with their status."""
    accounts = db.list_accounts()
    result = []
    for acc in accounts:
        result.append({
            "account_id": acc.get("account_id"),
            "user_id": acc.get("user_id"),
            "login_status": acc.get("login_status"),
            "created_at": acc.get("created_at"),
            "updated_at": acc.get("updated_at"),
        })
    return result


def delete_account(db: DatabaseManager, account_id: str) -> dict:
    """Delete a specific account and all its associated data."""
    account = db.get_account(account_id)
    if not account:
        return {"success": False, "error": f"Account not found: {account_id}"}
    
    db.delete_account(account_id)
    return {
        "success": True,
        "message": f"Account '{account_id}' and all associated data deleted",
    }


def clear_all_accounts(db: DatabaseManager) -> dict:
    """Clear all accounts and associated data (messages, contacts, login sessions)."""
    count = db.clear_all_accounts()
    return {
        "success": True,
        "message": f"Cleared {count} accounts and all associated data",
        "deleted_count": count,
    }


def get_account_status(db: DatabaseManager, account_id: str) -> dict:
    """Get status of a specific account."""
    account = db.get_account(account_id)
    if not account:
        return {"exists": False, "error": f"Account not found: {account_id}"}
    
    contacts = db.get_contacts(account_id)
    return {
        "exists": True,
        "account_id": account.get("account_id"),
        "user_id": account.get("user_id"),
        "login_status": account.get("login_status"),
        "contact_count": len(contacts),
        "base_url": account.get("base_url"),
        "updated_at": account.get("updated_at"),
    }
