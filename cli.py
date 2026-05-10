#!/usr/bin/env python3
"""
CLI for mcp-wechat-clawbot.
Usage:
  python cli.py login              QR code login
  python cli.py accounts [list]    List accounts
  python cli.py accounts delete <id>  Delete account
  python cli.py accounts clear     Clear all accounts
  python cli.py history            Show chat history
  python cli.py contacts           Show contacts
"""
import sys
import argparse
import json

from src.database import DatabaseManager
from src.login import handle_qr_login, check_existing_login
from src.account_manager import list_accounts, delete_account, clear_all_accounts
from src.message_handler import get_chat_history, get_contacts


def cmd_login(args):
    """Handle login command."""
    db = DatabaseManager()
    existing = check_existing_login(db)
    if existing and not args.force:
        print(f"Already logged in as: {existing['account_id']}")
        print("Use --force to login with a new account")
        return
    handle_qr_login(db)


def cmd_accounts(args):
    """Handle accounts command."""
    db = DatabaseManager()
    subcommand = args.subcommand or "list"
    
    if subcommand == "list":
        accounts = list_accounts(db)
        if not accounts:
            print("No accounts found.")
        else:
            print(f"Accounts ({len(accounts)}):\n")
            for acc in accounts:
                print(f"  ID: {acc['account_id']}")
                print(f"  User: {acc['user_id']}")
                print(f"  Status: {acc['login_status']}")
                print(f"  Updated: {acc['updated_at']}")
                print()
    elif subcommand == "delete":
        if not args.id:
            print("Error: account ID required")
            sys.exit(1)
        result = delete_account(db, args.id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif subcommand == "clear":
        result = clear_all_accounts(db)
        print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_history(args):
    """Handle history command."""
    db = DatabaseManager()
    messages = get_chat_history(
        db,
        account_id=args.account,
        from_user_id=args.from_user,
        limit=args.limit,
    )
    if not messages:
        print("No messages found.")
    else:
        print(json.dumps(messages, indent=2, ensure_ascii=False))


def cmd_contacts(args):
    """Handle contacts command."""
    db = DatabaseManager()
    contacts = get_contacts(db, account_id=args.account)
    if not contacts:
        print("No contacts found.")
    else:
        print(f"Contacts ({len(contacts)}):\n")
        for c in contacts:
            print(f"  User: {c['user_id']}")
            print(f"  Last: {c['last_text'] or '(no text)'}")
            print(f"  Seen: {c['last_seen']}")
            print(f"  Msgs: {c['msg_count']}")
            print()


def main():
    parser = argparse.ArgumentParser(description="mcp-wechat-clawbot CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    login_parser = subparsers.add_parser("login", help="QR code login")
    login_parser.add_argument("--force", action="store_true", help="Force new login")
    login_parser.set_defaults(func=cmd_login)
    
    accounts_parser = subparsers.add_parser("accounts", help="Manage accounts")
    accounts_parser.add_argument("subcommand", nargs="?", choices=["list", "delete", "clear"], default="list")
    accounts_parser.add_argument("--id", help="Account ID for delete")
    accounts_parser.set_defaults(func=cmd_accounts)
    
    history_parser = subparsers.add_parser("history", help="Show chat history")
    history_parser.add_argument("--account", help="Filter by account ID")
    history_parser.add_argument("--from-user", help="Filter by sender")
    history_parser.add_argument("--limit", type=int, default=50, help="Max messages")
    history_parser.set_defaults(func=cmd_history)
    
    contacts_parser = subparsers.add_parser("contacts", help="Show contacts")
    contacts_parser.add_argument("--account", help="Filter by account ID")
    contacts_parser.set_defaults(func=cmd_contacts)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
