"""
Main MCP server entry point.
Implements the Model Context Protocol server with tools for:
- Account management (list, delete, clear all)
- Message sending and polling
- Chat history queries
- Contact management
- QR code login
"""
import sys
import json
import signal
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.database import DatabaseManager
from src.login import login_or_use_existing, handle_qr_login, check_existing_login
from src.api import (
    DEFAULT_BASE_URL, send_text_message, get_updates,
    get_config, download_media, upload_media,
    send_image_message, send_file_message,
    WeixinAuthError, WeixinNetworkError
)
from src.account_manager import list_accounts, delete_account, clear_all_accounts, get_account_status
from src.message_handler import (
    poll_messages, get_chat_history, get_contacts, send_message
)
from src.thread_pool import ThreadPoolManager
from src.cursor_manager import CursorManager


server = Server("mcp-wechat-clawbot")


db = DatabaseManager()
cursor_manager = CursorManager()
thread_pool: Optional[ThreadPoolManager] = None


def format_error(error: Exception) -> str:
    """Format error message for tool response."""
    if isinstance(error, WeixinAuthError):
        return f"Authentication error: {error.message}. Please re-login."
    if isinstance(error, WeixinNetworkError):
        return f"Network error: {str(error)}"
    return f"Error: {str(error)}"


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [
        Tool(
            name="wechat_list_accounts",
            description="List all WeChat accounts with their status.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="wechat_delete_account",
            description="Delete a specific WeChat account and all associated data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "account_id": {"type": "string", "description": "Account ID to delete"},
                },
                "required": ["account_id"],
            },
        ),
        Tool(
            name="wechat_clear_all_accounts",
            description="Clear all WeChat accounts and associated data including chat messages, contacts, and login info.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="wechat_get_account_status",
            description="Get status of a specific WeChat account.",
            inputSchema={
                "type": "object",
                "properties": {
                    "account_id": {"type": "string", "description": "Account ID"},
                },
                "required": ["account_id"],
            },
        ),
        Tool(
            name="wechat_qr_login",
            description="Perform QR code login for a new WeChat account. Outputs QR code for scanning in the chat window.",
            inputSchema={
                "type": "object",
                "properties": {
                    "base_url": {"type": "string", "description": "Optional custom API base URL"},
                },
            },
        ),
        Tool(
            name="wechat_send",
            description="Send a WeChat text message. Uses the first available logged-in account or specify account_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient user ID"},
                    "text": {"type": "string", "description": "Message text"},
                    "account_id": {"type": "string", "description": "Optional account ID to use"},
                    "context_token": {"type": "string", "description": "Optional context token for reply"},
                },
                "required": ["to", "text"],
            },
        ),
        Tool(
            name="wechat_poll",
            description="Poll for new WeChat messages across all accounts or a specific account.",
            inputSchema={
                "type": "object",
                "properties": {
                    "account_id": {"type": "string", "description": "Optional account ID to poll"},
                    "reset_cursor": {"type": "boolean", "description": "Reset cursor and re-fetch from beginning"},
                },
            },
        ),
        Tool(
            name="wechat_contacts",
            description="List contacts who have messaged the bot. Use user_id as 'to' in wechat_send.",
            inputSchema={
                "type": "object",
                "properties": {
                    "account_id": {"type": "string", "description": "Optional account ID filter"},
                },
            },
        ),
        Tool(
            name="wechat_chat_history",
            description="Query chat message history with filters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "account_id": {"type": "string", "description": "Optional account ID filter"},
                    "from_user_id": {"type": "string", "description": "Optional sender filter"},
                    "limit": {"type": "integer", "description": "Number of messages to return (default: 50)"},
                    "offset": {"type": "integer", "description": "Offset for pagination (default: 0)"},
                },
            },
        ),
        Tool(
            name="wechat_send_image",
            description="Send an image to a WeChat user. Source can be a local file path or URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient user ID"},
                    "source": {"type": "string", "description": "Image source: local file path or URL"},
                    "account_id": {"type": "string", "description": "Optional account ID to use"},
                    "caption": {"type": "string", "description": "Optional text caption"},
                    "context_token": {"type": "string", "description": "Optional context token"},
                },
                "required": ["to", "source"],
            },
        ),
        Tool(
            name="wechat_send_file",
            description="Send a file attachment to a WeChat user.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient user ID"},
                    "source": {"type": "string", "description": "File source: local file path or URL"},
                    "account_id": {"type": "string", "description": "Optional account ID to use"},
                    "caption": {"type": "string", "description": "Optional text caption"},
                    "context_token": {"type": "string", "description": "Optional context token"},
                },
                "required": ["to", "source"],
            },
        ),
        Tool(
            name="wechat_get_config",
            description="Get bot config for a user (includes typing_ticket for typing indicators).",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "Target user ID"},
                    "account_id": {"type": "string", "description": "Optional account ID to use"},
                    "context_token": {"type": "string", "description": "Optional context token"},
                },
                "required": ["user_id"],
            },
        ),
        Tool(
            name="wechat_download",
            description="Download media (image/file/video) from a received message.",
            inputSchema={
                "type": "object",
                "properties": {
                    "encrypt_query_param": {"type": "string", "description": "encrypt_query_param from media item"},
                    "aes_key": {"type": "string", "description": "AES key (hex string) from media item"},
                },
                "required": ["encrypt_query_param", "aes_key"],
            },
        ),
    ]


def get_default_account() -> dict:
    """Get the first logged-in account."""
    accounts = db.list_accounts()
    for acc in accounts:
        if acc.get("login_status") == "logged_in" and acc.get("token"):
            return acc
    raise WeixinAuthError("No logged-in account found. Please perform QR login first.")


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    """Handle tool calls."""
    try:
        args = arguments or {}
        result = None
        
        if name == "wechat_list_accounts":
            result = list_accounts(db)
        
        elif name == "wechat_delete_account":
            account_id = args.get("account_id")
            if not account_id:
                raise ValueError("account_id is required")
            result = delete_account(db, account_id)
        
        elif name == "wechat_clear_all_accounts":
            result = clear_all_accounts(db)
        
        elif name == "wechat_get_account_status":
            account_id = args.get("account_id")
            if not account_id:
                raise ValueError("account_id is required")
            result = get_account_status(db, account_id)
        
        elif name == "wechat_qr_login":
            base_url = args.get("base_url", DEFAULT_BASE_URL)
            result = handle_qr_login(db, base_url)
        
        elif name == "wechat_send":
            to = args.get("to")
            text = args.get("text")
            if not to or not text:
                raise ValueError("to and text are required")
            
            account_id = args.get("account_id")
            if not account_id:
                account = get_default_account()
                account_id = account["account_id"]
            
            context_token = args.get("context_token")
            result = send_message(db, account_id, to, text, context_token)
        
        elif name == "wechat_poll":
            account_id = args.get("account_id")
            reset_cursor = args.get("reset_cursor", False)
            
            if account_id:
                account = db.get_account(account_id)
                if not account:
                    raise ValueError(f"Account not found: {account_id}")
                
                cursor = cursor_manager.load_cursor(account_id)
                if reset_cursor:
                    cursor = ""
                
                result = poll_messages(db, account_id, account["token"], 
                                       account.get("base_url", DEFAULT_BASE_URL), 
                                       cursor, reset_cursor)
            else:
                accounts = db.list_accounts()
                all_messages = []
                for acc in accounts:
                    if acc.get("login_status") == "logged_in" and acc.get("token"):
                        cursor = cursor_manager.load_cursor(acc["account_id"])
                        if reset_cursor:
                            cursor = ""
                        
                        resp = poll_messages(db, acc["account_id"], acc["token"],
                                             acc.get("base_url", DEFAULT_BASE_URL),
                                             cursor, reset_cursor)
                        all_messages.append({
                            "account_id": acc["account_id"],
                            "messages": resp["messages"],
                            "message_count": resp["message_count"],
                        })
                
                result = {"accounts": all_messages}
        
        elif name == "wechat_contacts":
            account_id = args.get("account_id")
            result = get_contacts(db, account_id)
        
        elif name == "wechat_chat_history":
            account_id = args.get("account_id")
            from_user_id = args.get("from_user_id")
            limit = args.get("limit", 50)
            offset = args.get("offset", 0)
            result = get_chat_history(db, account_id, from_user_id, limit, offset)
        
        elif name == "wechat_send_image":
            to = args.get("to")
            source = args.get("source")
            if not to or not source:
                raise ValueError("to and source are required")
            
            account_id = args.get("account_id")
            if not account_id:
                account = get_default_account()
                account_id = account["account_id"]
            else:
                account = db.get_account(account_id)
            
            if not account:
                raise ValueError(f"Account not found: {account_id}")
            
            uploaded = upload_media(source, "image", to, account["token"], 
                                    account.get("base_url", DEFAULT_BASE_URL))
            result = send_image_message(to, uploaded, account["token"],
                                        account.get("base_url", DEFAULT_BASE_URL),
                                        args.get("context_token"), args.get("caption"))
        
        elif name == "wechat_send_file":
            to = args.get("to")
            source = args.get("source")
            if not to or not source:
                raise ValueError("to and source are required")
            
            account_id = args.get("account_id")
            if not account_id:
                account = get_default_account()
                account_id = account["account_id"]
            else:
                account = db.get_account(account_id)
            
            if not account:
                raise ValueError(f"Account not found: {account_id}")
            
            uploaded = upload_media(source, "file", to, account["token"],
                                    account.get("base_url", DEFAULT_BASE_URL))
            result = send_file_message(to, uploaded, account["token"],
                                       account.get("base_url", DEFAULT_BASE_URL),
                                       args.get("context_token"), args.get("caption"))
        
        elif name == "wechat_get_config":
            user_id = args.get("user_id")
            if not user_id:
                raise ValueError("user_id is required")
            
            account_id = args.get("account_id")
            if not account_id:
                account = get_default_account()
                account_id = account["account_id"]
            else:
                account = db.get_account(account_id)
            
            if not account:
                raise ValueError(f"Account not found: {account_id}")
            
            result = get_config(user_id, account["token"],
                                account.get("base_url", DEFAULT_BASE_URL),
                                args.get("context_token"))
        
        elif name == "wechat_download":
            encrypt_query_param = args.get("encrypt_query_param")
            aes_key = args.get("aes_key")
            if not encrypt_query_param or not aes_key:
                raise ValueError("encrypt_query_param and aes_key are required")
            
            data = download_media(encrypt_query_param, aes_key)
            import base64
            result = {
                "success": True,
                "size": len(data),
                "base64": base64.b64encode(data).decode('utf-8'),
            }
        
        else:
            raise ValueError(f"Unknown tool: {name}")
        
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    
    except Exception as e:
        return [TextContent(type="text", text=format_error(e))]


def main():
    """Main entry point for the MCP server."""
    global thread_pool
    
    thread_pool = ThreadPoolManager(db, cursor_manager)
    thread_pool.start_all_accounts()
    
    def signal_handler(sig, frame):
        print("\nShutting down...")
        if thread_pool:
            thread_pool.stop_all()
        db.close_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("WeChat MCP Clawbot server starting...", file=sys.stderr)
    print(f"Database: {db._db_path}", file=sys.stderr)
    
    accounts = db.list_accounts()
    print(f"Loaded {len(accounts)} account(s)", file=sys.stderr)
    
    async def run_server():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream)
    
    import asyncio
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
