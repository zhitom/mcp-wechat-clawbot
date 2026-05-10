"""
Message handler for recording and querying chat messages.
Handles message polling, storage, and history queries.
"""
import json
from typing import Optional

from src.database import DatabaseManager
from src.api import get_updates, send_text_message


def process_received_messages(db: DatabaseManager, account_id: str, messages: list) -> int:
    """Process and store received messages in the database."""
    count = 0
    for msg in messages:
        from_user_id = msg.get("from_user_id", "")
        to_user_id = msg.get("to_user_id", "")
        message_type = msg.get("message_type", 0)
        message_id = msg.get("message_id")
        message_state = msg.get("message_state")
        context_token = msg.get("context_token")
        
        text_content = None
        item_list = msg.get("item_list", [])
        for item in item_list:
            if item.get("type") == 1:
                text_item = item.get("text_item", {})
                if text_item:
                    text_content = text_item.get("text")
                    break
        
        raw_message = json.dumps(msg)
        
        db.add_chat_message(
            account_id=account_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            message_type=message_type,
            text_content=text_content,
            message_id=message_id,
            message_state=message_state,
            context_token=context_token,
            raw_message=raw_message,
        )
        
        if from_user_id and message_type != 2:
            db.update_contact(
                account_id=account_id,
                user_id=from_user_id,
                last_text=text_content,
                context_token=context_token,
            )
        
        count += 1
    
    return count


def poll_messages(db: DatabaseManager, account_id: str, token: str,
                  base_url: str, cursor: str = "",
                  reset_cursor: bool = False) -> dict:
    """Poll for new messages and store them in the database."""
    if reset_cursor:
        cursor = ""
    
    response = get_updates(token, base_url, cursor)
    
    messages = response.get("msgs", [])
    new_cursor = response.get("get_updates_buf", cursor)
    
    if messages:
        processed = process_received_messages(db, account_id, messages)
    else:
        processed = 0
    
    return {
        "messages": messages,
        "message_count": len(messages),
        "processed_count": processed,
        "cursor": new_cursor,
    }


def get_chat_history(db: DatabaseManager, account_id: Optional[str] = None,
                     from_user_id: Optional[str] = None,
                     limit: int = 50, offset: int = 0) -> list:
    """Get chat message history."""
    messages = db.get_chat_history(
        account_id=account_id,
        from_user_id=from_user_id,
        limit=limit,
        offset=offset,
    )
    
    result = []
    for msg in messages:
        result.append({
            "id": msg.get("id"),
            "account_id": msg.get("account_id"),
            "from_user_id": msg.get("from_user_id"),
            "to_user_id": msg.get("to_user_id"),
            "message_type": msg.get("message_type"),
            "text_content": msg.get("text_content"),
            "context_token": msg.get("context_token"),
            "created_at": msg.get("created_at"),
        })
    
    return result


def get_contacts(db: DatabaseManager, account_id: Optional[str] = None) -> list:
    """Get contacts list."""
    contacts = db.get_contacts(account_id)
    
    result = []
    for contact in contacts:
        result.append({
            "account_id": contact.get("account_id"),
            "user_id": contact.get("user_id"),
            "last_seen": contact.get("last_seen"),
            "last_text": contact.get("last_text"),
            "context_token": contact.get("context_token"),
            "msg_count": contact.get("msg_count"),
        })
    
    return result


def send_message(db: DatabaseManager, account_id: str, to: str, text: str,
                 context_token: Optional[str] = None) -> dict:
    """Send a text message and record it in the database."""
    account = db.get_account(account_id)
    if not account:
        return {"success": False, "error": f"Account not found: {account_id}"}
    
    token = account.get("token")
    base_url = account.get("base_url")
    
    response = send_text_message(to, text, token, base_url, context_token)
    
    db.add_chat_message(
        account_id=account_id,
        from_user_id="",
        to_user_id=to,
        message_type=2,
        message_state=2,
        text_content=text,
        context_token=context_token,
    )
    
    return {
        "success": True,
        "response": response,
    }
