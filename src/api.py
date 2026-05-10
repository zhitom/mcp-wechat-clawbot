"""
WeChat API client module for communicating with the WeChat bot API.
Uses requests for HTTP communication.
"""
import json
import uuid
import base64
import time
from typing import Optional
from dataclasses import dataclass, field

import requests


DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
CHANNEL_VERSION = "1.0.2"
BOT_TYPE = "3"


class WeixinAuthError(Exception):
    """Authentication error."""
    pass


class WeixinNetworkError(Exception):
    """Network error."""
    pass


@dataclass
class UploadedMedia:
    filekey: str
    download_encrypted_query_param: str
    aeskey: str
    file_size: int
    file_size_ciphertext: int
    file_name: Optional[str] = None


def generate_client_id() -> str:
    return f"weixin-mcp-{uuid.uuid4().hex[:16]}"


def random_wechat_uin() -> str:
    import os
    return base64.b64encode(os.urandom(4)).decode('utf-8')


def build_headers(token: str, body_str: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Content-Length": str(len(body_str.encode('utf-8'))),
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "X-WECHAT-UIN": random_wechat_uin(),
    }


def weixin_request(endpoint: str, body: dict, token: str, 
                   base_url: str = DEFAULT_BASE_URL, retries: int = 1) -> dict:
    """Make a request to the Weixin API."""
    base = base_url.rstrip('/') + '/'
    url = f"{base}{endpoint}"
    body_str = json.dumps(body)
    
    last_error = None
    for attempt in range(retries + 1):
        try:
            headers = build_headers(token, body_str)
            response = requests.post(url, headers=headers, data=body_str, timeout=30)
            
            if response.status_code in (401, 403):
                raise WeixinAuthError("Authentication failed. Please re-login.")
            
            if not response.ok:
                raise requests.HTTPError(
                    f"Weixin API error {response.status_code}: {response.text.strip()}"
                )
            
            return response.json()
        except requests.RequestException as e:
            last_error = e
            if attempt < retries:
                time.sleep(1)
                continue
            raise WeixinNetworkError(f"Network request failed: {e}")
    
    raise WeixinNetworkError("Network request failed after retries")


def fetch_qr_code(base_url: str = DEFAULT_BASE_URL) -> dict:
    """Fetch QR code for login."""
    base = base_url.rstrip('/') + '/'
    url = f"{base}ilink/bot/get_bot_qrcode?bot_type={BOT_TYPE}"
    response = requests.get(url, timeout=30)
    if not response.ok:
        raise Exception(f"QR fetch failed: {response.status_code}")
    return response.json()


def poll_qr_status(qrcode_token: str, base_url: str = DEFAULT_BASE_URL) -> dict:
    """Poll QR code login status."""
    base = base_url.rstrip('/') + '/'
    url = f"{base}ilink/bot/get_qrcode_status?qrcode={requests.utils.quote(qrcode_token)}"
    headers = {"iLink-App-ClientVersion": "1"}
    response = requests.get(url, headers=headers, timeout=30)
    if not response.ok:
        raise Exception(f"Status poll failed: {response.status_code}")
    return response.json()


def send_text_message(to: str, text: str, token: str, 
                      base_url: str = DEFAULT_BASE_URL, 
                      context_token: Optional[str] = None) -> dict:
    """Send a text message."""
    body = {
        "msg": {
            "from_user_id": "",
            "to_user_id": to,
            "client_id": generate_client_id(),
            "message_type": 2,
            "message_state": 2,
            "item_list": [{"type": 1, "text_item": {"text": text}}],
        },
        "base_info": {"channel_version": CHANNEL_VERSION},
    }
    if context_token:
        body["msg"]["context_token"] = context_token
    
    return weixin_request("ilink/bot/sendmessage", body, token, base_url)


def get_updates(token: str, base_url: str = DEFAULT_BASE_URL, 
                cursor: str = "") -> dict:
    """Poll for new messages."""
    body = {
        "get_updates_buf": cursor,
        "base_info": {"channel_version": CHANNEL_VERSION},
    }
    return weixin_request("ilink/bot/getupdates", body, token, base_url)


def get_config(user_id: str, token: str, base_url: str = DEFAULT_BASE_URL,
               context_token: Optional[str] = None) -> dict:
    """Get bot config for a user."""
    body = {
        "ilink_userId": user_id,
        "base_info": {"channel_version": CHANNEL_VERSION},
    }
    if context_token:
        body["context_token"] = context_token
    
    return weixin_request("ilink/bot/getconfig", body, token, base_url)


def upload_media(source: str, media_type: str, to_user_id: str, 
                 token: str, base_url: str = DEFAULT_BASE_URL) -> UploadedMedia:
    """Upload media file to WeChat."""
    import os
    
    if source.startswith(('http://', 'https://')):
        response = requests.get(source, timeout=60)
        response.raise_for_status()
        file_content = response.content
        file_name = os.path.basename(source) or "file"
    else:
        with open(source, 'rb') as f:
            file_content = f.read()
        file_name = os.path.basename(source)
    
    file_size = len(file_content)
    import hashlib
    file_hash = hashlib.md5(file_content).hexdigest()
    
    body = {
        "file_key": file_hash,
        "file_size": file_size,
        "file_name": file_name,
        "to_user_id": to_user_id,
        "media_type": media_type,
        "base_info": {"channel_version": CHANNEL_VERSION},
    }
    
    result = weixin_request("ilink/bot/uploadmedia", body, token, base_url)
    
    return UploadedMedia(
        filekey=result.get("filekey", file_hash),
        download_encrypted_query_param=result.get("downloadEncryptedQueryParam", ""),
        aeskey=result.get("aeskey", ""),
        file_size=file_size,
        file_size_ciphertext=result.get("fileSizeCiphertext", file_size),
        file_name=file_name,
    )


def send_image_message(to: str, uploaded: UploadedMedia, token: str,
                       base_url: str = DEFAULT_BASE_URL,
                       context_token: Optional[str] = None,
                       caption: Optional[str] = None) -> dict:
    """Send an image message."""
    items = []
    if caption:
        items.append({"type": 1, "text_item": {"text": caption}})
    
    items.append({
        "type": 2,
        "image_item": {
            "media": {
                "encrypt_query_param": uploaded.download_encrypted_query_param,
                "aes_key": base64.b64encode(uploaded.aeskey.encode('utf-8')).decode('utf-8'),
                "encrypt_type": 1,
            },
            "aeskey": uploaded.aeskey,
            "mid_size": uploaded.file_size_ciphertext,
        },
    })
    
    for item in items:
        body = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to,
                "client_id": generate_client_id(),
                "message_type": 2,
                "message_state": 2,
                "item_list": [item],
            },
            "base_info": {"channel_version": CHANNEL_VERSION},
        }
        if context_token:
            body["msg"]["context_token"] = context_token
        
        weixin_request("ilink/bot/sendmessage", body, token, base_url)
    
    return {"success": True, "filekey": uploaded.filekey}


def send_file_message(to: str, uploaded: UploadedMedia, token: str,
                      base_url: str = DEFAULT_BASE_URL,
                      context_token: Optional[str] = None,
                      caption: Optional[str] = None) -> dict:
    """Send a file message."""
    items = []
    if caption:
        items.append({"type": 1, "text_item": {"text": caption}})
    
    items.append({
        "type": 4,
        "file_item": {
            "media": {
                "encrypt_query_param": uploaded.download_encrypted_query_param,
                "aes_key": base64.b64encode(uploaded.aeskey.encode('utf-8')).decode('utf-8'),
                "encrypt_type": 1,
            },
            "file_name": uploaded.file_name or "file",
            "len": str(uploaded.file_size),
        },
    })
    
    for item in items:
        body = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to,
                "client_id": generate_client_id(),
                "message_type": 2,
                "message_state": 2,
                "item_list": [item],
            },
            "base_info": {"channel_version": CHANNEL_VERSION},
        }
        if context_token:
            body["msg"]["context_token"] = context_token
        
        weixin_request("ilink/bot/sendmessage", body, token, base_url)
    
    return {"success": True, "filekey": uploaded.filekey, "fileName": uploaded.file_name}


def download_media(encrypt_query_param: str, aes_key: str,
                   base_url: str = DEFAULT_BASE_URL) -> bytes:
    """Download media from WeChat."""
    base = base_url.rstrip('/') + '/'
    url = f"{base}ilink/bot/downloadmedia?{encrypt_query_param}"
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    
    encrypted_data = response.content
    
    import hashlib
    key_bytes = bytes.fromhex(aes_key) if len(aes_key) == 64 else aes_key.encode('utf-8')
    
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        
        cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(key_bytes), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted_data) + decryptor.finalize()
        return decrypted
    except ImportError:
        return encrypted_data
