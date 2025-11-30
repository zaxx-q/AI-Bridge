#!/usr/bin/env python3
"""
Chat session management with persistence
"""

import json
import threading
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from .config import SESSIONS_FILE

# Global session storage
CHAT_SESSIONS = OrderedDict()
SESSION_LOCK = threading.Lock()


class ChatSession:
    """Represents a chat session with history"""
    
    def __init__(self, session_id=None, endpoint=None, provider=None, model=None, image_base64=None, mime_type=None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.endpoint = endpoint or "chat"
        self.provider = provider or "google"
        self.model = model  # Optional model override
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.image_base64 = image_base64
        self.mime_type = mime_type or "image/png"
        self.messages = []
        self.title = None
    
    def add_message(self, role, content):
        """Add a message to the session"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self.updated_at = datetime.now().isoformat()
        if not self.title and role == "user":
            self.title = content[:50] + ("..." if len(content) > 50 else "")
    
    def get_conversation_for_api(self, include_image=True):
        """Convert session messages to API format"""
        messages = []
        for i, msg in enumerate(self.messages):
            if msg["role"] == "user":
                content = []
                if i == 0 and include_image and self.image_base64:
                    data_url = f"data:{self.mime_type};base64,{self.image_base64}"
                    content.append({"type": "image_url", "image_url": {"url": data_url}})
                content.append({"type": "text", "text": msg["content"]})
                messages.append({"role": "user", "content": content})
            else:
                messages.append({"role": "assistant", "content": msg["content"]})
        return messages
    
    def to_dict(self):
        """Convert session to dictionary for serialization"""
        return {
            "session_id": self.session_id,
            "endpoint": self.endpoint,
            "provider": self.provider,
            "model": self.model,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "title": self.title,
            "messages": self.messages,
            "has_image": bool(self.image_base64),
            "mime_type": self.mime_type
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create session from dictionary"""
        session = cls()
        session.session_id = data.get("session_id", str(uuid.uuid4())[:8])
        session.endpoint = data.get("endpoint", "chat")
        session.provider = data.get("provider", "google")
        session.model = data.get("model")
        session.created_at = data.get("created_at", datetime.now().isoformat())
        session.updated_at = data.get("updated_at", session.created_at)
        session.title = data.get("title")
        session.messages = data.get("messages", [])
        session.mime_type = data.get("mime_type", "image/png")
        session.image_base64 = None
        return session


def save_sessions():
    """Save all sessions to file"""
    with SESSION_LOCK:
        try:
            data = {sid: session.to_dict() for sid, session in CHAT_SESSIONS.items()}
            with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Warning] Failed to save sessions: {e}")


def load_sessions():
    """Load sessions from file"""
    global CHAT_SESSIONS
    try:
        if Path(SESSIONS_FILE).exists():
            with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            with SESSION_LOCK:
                for sid, session_data in data.items():
                    CHAT_SESSIONS[sid] = ChatSession.from_dict(session_data)
            print(f"  ✓ Loaded {len(CHAT_SESSIONS)} saved session(s)")
    except Exception as e:
        print(f"[Warning] Failed to load sessions: {e}")


def add_session(session, max_sessions=50):
    """Add a session and manage max limit"""
    with SESSION_LOCK:
        while len(CHAT_SESSIONS) >= max_sessions:
            oldest_id = next(iter(CHAT_SESSIONS))
            del CHAT_SESSIONS[oldest_id]
        CHAT_SESSIONS[session.session_id] = session
    threading.Thread(target=save_sessions, daemon=True).start()


def get_session(session_id):
    """Get a session by ID"""
    with SESSION_LOCK:
        return CHAT_SESSIONS.get(session_id)


def list_sessions():
    """List all sessions in reverse chronological order"""
    with SESSION_LOCK:
        sessions = []
        for sid, session in reversed(list(CHAT_SESSIONS.items())):
            sessions.append({
                "id": sid,
                "title": session.title or "(No title)",
                "endpoint": session.endpoint,
                "provider": session.provider,
                "messages": len(session.messages),
                "updated": session.updated_at,
                "created": session.created_at
            })
        return sessions


def delete_session(session_id):
    """Delete a session by ID"""
    with SESSION_LOCK:
        if session_id in CHAT_SESSIONS:
            del CHAT_SESSIONS[session_id]
            return True
        return False


def clear_all_sessions():
    """Clear all sessions"""
    with SESSION_LOCK:
        CHAT_SESSIONS.clear()
