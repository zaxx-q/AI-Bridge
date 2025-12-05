#!/usr/bin/env python3
"""
Flask web server with API endpoints
"""

import base64
import time

from flask import Flask, request, abort, jsonify

from .config import CONFIG_FILE
from .api_client import call_api_simple, call_api_chat
from .session_manager import ChatSession, add_session, get_session, list_sessions
from .gui.core import show_chat_gui, show_session_browser, get_gui_status, HAVE_GUI

# Global state - will be initialized by main.py
CONFIG = {}
AI_PARAMS = {}
ENDPOINTS = {}
KEY_MANAGERS = {}

app = Flask(__name__)


def create_endpoint_handler(endpoint_name, prompt_template):
    """Create a handler function for a specific endpoint"""
    def handler():
        start_time = time.time()
        
        image_bytes = None
        mime_type = 'image/png'
        
        if 'image' in request.files:
            image_file = request.files['image']
            image_bytes = image_file.read()
            mime_type = image_file.mimetype or 'image/png'
        elif request.content_type and 'image' in request.content_type:
            image_bytes = request.get_data()
            mime_type = request.content_type.split(';')[0]
        elif request.data:
            image_bytes = request.data
        
        if not image_bytes:
            abort(400, description='No image found in request.')
        
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        # Parse provider override
        provider = CONFIG.get("default_provider", "google")
        if request.args.get('provider'):
            provider = request.args.get('provider').lower()
        elif request.headers.get('X-API-Provider'):
            provider = request.headers.get('X-API-Provider').lower()
        
        # Parse prompt override
        prompt = prompt_template
        if request.args.get('prompt'):
            prompt = request.args.get('prompt')
        elif request.headers.get('X-Custom-Prompt'):
            prompt = request.headers.get('X-Custom-Prompt')
        
        # Parse model override
        model_override = None
        if request.args.get('model'):
            model_override = request.args.get('model')
        elif request.headers.get('X-API-Model'):
            model_override = request.headers.get('X-API-Model')
        
        # Determine the effective model for logging
        if model_override:
            effective_model = model_override
        elif provider == "openrouter":
            effective_model = CONFIG.get("openrouter_model", "google/gemini-2.5-flash-preview")
        elif provider == "google":
            effective_model = CONFIG.get("google_model", "gemini-2.0-flash")
        elif provider == "custom":
            effective_model = CONFIG.get("custom_model", "not configured")
        else:
            effective_model = "unknown"
        
        # Show parameter: yes/true/1 = show chat window, anything else = no
        show_param = request.args.get('show', CONFIG.get('default_show', 'no'))
        if isinstance(show_param, bool):
            show_gui = show_param
        else:
            show_gui = str(show_param).lower() in ('yes', 'true', '1')
        
        # Enhanced request logging
        print(f"\n{'='*60}")
        print(f"[{endpoint_name.upper()}] New request")
        print(f"  Provider: {provider}")
        print(f"  Model: {effective_model}{' (override)' if model_override else ' (default)'}")
        print(f"  Image: {len(image_bytes) / 1024:.1f} KB ({mime_type})")
        print(f"  Show GUI: {show_gui}")
        print(f"  Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
        
        result, error = call_api_simple(
            provider, prompt, base64_image, mime_type, model_override,
            CONFIG, AI_PARAMS, KEY_MANAGERS
        )
        elapsed = time.time() - start_time
        
        if error:
            print(f"  [FAILED] {error} ({elapsed:.1f}s)")
            print(f"{'='*60}\n")
            return jsonify({"error": error, "elapsed": elapsed}), 500
        
        print(f"  [SUCCESS] {len(result)} chars ({elapsed:.1f}s)")
        print(f"{'='*60}\n")
        
        # Show chat window if requested
        if show_gui and HAVE_GUI:
            session = ChatSession(
                endpoint=endpoint_name,
                provider=provider,
                model=model_override,
                image_base64=base64_image,
                mime_type=mime_type
            )
            session.add_message("user", prompt)
            session.add_message("assistant", result)
            add_session(session, CONFIG.get("max_sessions", 50))
            show_chat_gui(session, initial_response=result)
        
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"text": result, "elapsed": elapsed})
        
        return result, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    
    handler.__name__ = f"handle_{endpoint_name}"
    return handler


@app.route('/')
def index():
    """Root endpoint with service information"""
    available_providers = [p for p, km in KEY_MANAGERS.items() if km.has_keys()]
    return jsonify({
        "service": "AI Bridge",
        "status": "running",
        "gui_available": HAVE_GUI,
        "gui_running": get_gui_status()["running"],
        "default_provider": CONFIG.get("default_provider", "google"),
        "available_providers": available_providers,
        "endpoints": {f"/{name}": prompt[:100] + "..." if len(prompt) > 100 else prompt 
                     for name, prompt in ENDPOINTS.items()},
        "show_parameter": {
            "yes": "Show result in a chat GUI window",
            "no": "Return text only (default)"
        },
        "sessions": len(list_sessions())
    })


@app.route('/health')
def health():
    """Health check endpoint"""
    gui_status = get_gui_status()
    return jsonify({
        "status": "healthy",
        "gui_available": HAVE_GUI,
        "gui_running": gui_status["running"],
        "providers": {p: km.get_key_count() for p, km in KEY_MANAGERS.items() if km.has_keys()},
        "endpoints_count": len(ENDPOINTS),
        "sessions_count": len(list_sessions())
    })


@app.route('/sessions')
def sessions_list():
    """List all chat sessions"""
    return jsonify(list_sessions())


@app.route('/sessions/<session_id>')
def get_session_api(session_id):
    """Get a specific session"""
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(session.to_dict())


@app.route('/gui/browser')
def open_browser_api():
    """Open the session browser via HTTP request"""
    if show_session_browser():
        return jsonify({"status": "ok", "message": "Session browser opened"})
    else:
        return jsonify({"status": "error", "message": "GUI not available"}), 503


@app.errorhandler(400)
def bad_request(e):
    """Handle 400 errors"""
    return jsonify({"error": str(e.description)}), 400


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors"""
    return jsonify({"error": "Internal server error"}), 500


def init_web_server(config, ai_params, endpoints, key_managers):
    """Initialize web server with configuration"""
    global CONFIG, AI_PARAMS, ENDPOINTS, KEY_MANAGERS
    CONFIG = config
    AI_PARAMS = ai_params
    ENDPOINTS = endpoints
    KEY_MANAGERS = key_managers
    
    # Register dynamic endpoints
    for endpoint_name, prompt in endpoints.items():
        handler = create_endpoint_handler(endpoint_name, prompt)
        app.add_url_rule(f'/{endpoint_name}', endpoint_name, handler, methods=['POST'])
    
    return app
