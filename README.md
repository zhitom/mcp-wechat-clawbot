# mcp-wechat-clawbot

MCP server for WeChat with multi-account support, SQLite storage, QR code login, and thread pool concurrency.

## Overview

This project implements a WeChat MCP (Model Context Protocol) server that:

- Supports multiple WeChat accounts per MCP service
- Stores account information in SQLite database
- Displays QR code for scanning login in the chat window
- Records chat messages to SQLite for history queries
- Provides tools for account management (list, delete, clear all)
- Uses Python with thread pool concurrency to avoid GIL issues

## Features

### Multi-Account Support
- Multiple WeChat accounts managed by a single MCP service
- Account information stored in SQLite database
- Each account has its own polling worker thread

### QR Code Login
- QR code displayed in terminal for scanning
- Login status recorded in SQLite database
- Existing sessions automatically reused

### Chat History
- All messages recorded to SQLite
- Query history by account or sender
- Pagination support for large datasets

### Account Management Tools
- List all accounts
- Delete specific accounts (including all associated data)
- Clear all accounts (messages, contacts, login info)

### Concurrency
- Thread pool for concurrent account polling
- WAL mode SQLite for better concurrent read/write
- Connection-per-thread pattern to avoid GIL issues

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### QR Code Login

```bash
python cli.py login
```

### Start MCP Server

```bash
python -m src.main
```

Or with the CLI:

```bash
python cli.py accounts list
python cli.py history
python cli.py contacts
```

## MCP Tools

### Account Management
- `wechat_list_accounts` - List all accounts
- `wechat_delete_account` - Delete an account
- `wechat_clear_all_accounts` - Clear all accounts
- `wechat_get_account_status` - Get account status

### Login
- `wechat_qr_login` - QR code login

### Messaging
- `wechat_send` - Send text message
- `wechat_send_image` - Send image
- `wechat_send_file` - Send file
- `wechat_poll` - Poll for new messages
- `wechat_contacts` - List contacts
- `wechat_chat_history` - Query chat history

### Other
- `wechat_get_config` - Get bot config
- `wechat_download` - Download media

## Project Structure

```
mcp-wechat-clawbot/
├── src/
│   ├── __init__.py
│   ├── main.py              # MCP server entry point
│   ├── api.py               # WeChat API client
│   ├── database.py          # SQLite database manager
│   ├── login.py             # QR code login handler
│   ├── account_manager.py   # Account management tools
│   ├── message_handler.py   # Message processing
│   ├── thread_pool.py       # Thread pool manager
│   └── cursor_manager.py    # Polling cursor persistence
├── cli.py                   # CLI tool
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Database

SQLite database stored at `~/.mcp-wechat-clawbot/clawbot.db` with tables:
- `accounts` - Account information and tokens
- `chat_messages` - Chat message history
- `contacts` - Contact book
- `login_sessions` - Login session records

## Repository

GitHub: <https://github.com/zhitom/mcp-wechat-clawbot.git>
