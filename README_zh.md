# mcp-wechat-clawbot

支持多账号、SQLite存储、二维码登录和线程池并发的微信MCP服务器。

## 概述

本项目实现了一个微信MCP（Model Context Protocol）服务器，具备以下特性：

- 一个MCP服务支持多个微信账号
- 账号信息存储在SQLite数据库中
- 在聊天窗口中显示二维码进行扫码登录
- 将聊天消息记录到SQLite数据库，支持历史消息查询
- 提供账号管理工具（列表、删除、清空）
- 使用Python配合线程池并发，避免GIL问题

## 功能特性

### 多账号支持
- 单个MCP服务管理多个微信账号
- 账号信息存储在SQLite数据库中
- 每个账号拥有独立的轮询工作线程

### 二维码登录
- 在终端中显示二维码供扫描
- 登录状态记录在SQLite数据库中
- 已有会话自动复用，无需重复登录

### 聊天历史
- 所有消息均记录到SQLite数据库
- 可按账号或发送者查询历史记录
- 大数据量支持分页查询

### 账号管理工具
- 列出所有账号
- 删除指定账号（包括所有关联数据）
- 清空所有账号（消息、联系人、登录信息）

### 并发处理
- 线程池用于并发轮询多个账号
- WAL模式SQLite提升并发读写性能
- 每线程独立连接模式避免GIL问题

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 二维码登录

```bash
python cli.py login
```

### 启动MCP服务器

```bash
python -m src.main
```

或使用CLI工具：

```bash
python cli.py accounts list     # 查看账号列表
python cli.py history           # 查看聊天历史
python cli.py contacts          # 查看联系人列表
```

## MCP工具列表

### 账号管理
- `wechat_list_accounts` - 列出所有账号
- `wechat_delete_account` - 删除指定账号
- `wechat_clear_all_accounts` - 清空所有账号
- `wechat_get_account_status` - 获取账号状态

### 登录
- `wechat_qr_login` - 二维码扫码登录

### 消息
- `wechat_send` - 发送文本消息
- `wechat_send_image` - 发送图片
- `wechat_send_file` - 发送文件
- `wechat_poll` - 轮询新消息
- `wechat_contacts` - 列出联系人
- `wechat_chat_history` - 查询聊天历史

### 其他
- `wechat_get_config` - 获取机器人配置
- `wechat_download` - 下载媒体文件

## 项目结构

```
mcp-wechat-clawbot/
├── src/
│   ├── __init__.py
│   ├── main.py              # MCP服务器入口
│   ├── api.py               # 微信API客户端
│   ├── database.py          # SQLite数据库管理
│   ├── login.py             # 二维码登录处理
│   ├── account_manager.py   # 账号管理工具
│   ├── message_handler.py   # 消息处理
│   ├── thread_pool.py       # 线程池管理
│   └── cursor_manager.py    # 轮询游标持久化
├── cli.py                   # 命令行工具
├── requirements.txt
├── pyproject.toml
└── README.md
```

## 数据库

SQLite数据库存储在 `~/.mcp-wechat-clawbot/clawbot.db`，包含以下表：

| 表名 | 说明 |
|------|------|
| `accounts` | 账号信息和token |
| `chat_messages` | 聊天消息历史记录 |
| `contacts` | 联系人列表 |
| `login_sessions` | 登录会话记录 |

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `WEIXIN_MCP_DIR` | 自定义账号目录路径 | `~/.mcp-wechat-clawbot` |

### 数据库配置

- 使用WAL模式（Write-Ahead Logging）提升并发性能
- 设置5秒忙碌超时，避免并发冲突
- 启用外键约束保证数据一致性

## 使用示例

### 登录新账号

```bash
python cli.py login
```

系统会在终端中显示二维码，使用微信扫描即可完成登录。

### 强制重新登录

```bash
python cli.py login --force
```

### 查看所有账号

```bash
python cli.py accounts list
```

输出示例：
```
Accounts (2):

  ID: abc123-im-bot
  User: user1@im.wechat
  Status: logged_in
  Updated: 2024-01-01T12:00:00

  ID: def456-im-bot
  User: user2@im.wechat
  Status: logged_in
  Updated: 2024-01-01T11:00:00
```

### 删除账号

```bash
python cli.py accounts delete --id abc123-im-bot
```

### 清空所有账号

```bash
python cli.py accounts clear
```

### 查看聊天历史

```bash
python cli.py history --limit 20
```

### 按发送者过滤消息

```bash
python cli.py history --from-user wxid_xxx
```

## 依赖要求

- Python >= 3.10
- mcp >= 1.0.0
- qrcode-terminal >= 0.1.0
- requests >= 2.31.0

## 常见问题

### Q: 二维码过期怎么办？

A: 二维码会在过期后自动刷新，最多刷新3次。如果3次都过期，请重新运行登录命令。

### Q: 如何切换默认使用的账号？

A: MCP工具支持通过 `account_id` 参数指定使用哪个账号。不指定时默认使用第一个已登录的账号。

### Q: 数据库文件在哪里？

A: 默认位于 `~/.mcp-wechat-clawbot/clawbot.db`，可以通过设置 `WEIXIN_MCP_DIR` 环境变量自定义路径。

## 仓库地址

GitHub: <https://github.com/zhitom/mcp-wechat-clawbot.git>
