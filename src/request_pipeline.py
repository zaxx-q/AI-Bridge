#!/usr/bin/env python3
"""
Unified API Request Pipeline
All API requests flow through this module for consistent logging and handling
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable, Dict, Any
import time

class RequestOrigin(Enum):
    CHAT_WINDOW = "chat_window"
    POPUP_INPUT = "popup_input"
    POPUP_PROMPT = "popup_prompt"  
    ENDPOINT_OCR = "endpoint/ocr"
    ENDPOINT_TRANSLATE = "endpoint/translate"
    ENDPOINT_DESCRIBE = "endpoint/describe"
    ENDPOINT_SUMMARIZE = "endpoint/summarize"
    ENDPOINT_TEXTEDIT = "endpoint/textedit"

@dataclass
class RequestContext:
    """Context for a single API request"""
    origin: RequestOrigin
    provider: str
    model: str
    streaming: bool
    thinking_enabled: bool
    session_id: Optional[str] = None
    
    # Populated after response
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated: bool = False
    elapsed_time: float = 0.0
    response_text: str = ""
    reasoning_text: str = ""
    error: Optional[str] = None

@dataclass  
class StreamCallback:
    """Callbacks for streaming response handling"""
    on_text: Optional[Callable[[str], None]] = None
    on_thinking: Optional[Callable[[str], None]] = None
    on_usage: Optional[Callable[[Dict], None]] = None
    on_done: Optional[Callable[[], None]] = None
    on_error: Optional[Callable[[str], None]] = None

class RequestPipeline:
    """Unified request pipeline with mandatory logging"""
    
    @staticmethod
    def log_request_start(ctx: RequestContext):
        """Log when request starts"""
        print(f"\n{'='*60}")
        print(f"[API REQUEST] {ctx.origin.value}")
        print(f"  Provider: {ctx.provider}")
        print(f"  Model: {ctx.model}")
        print(f"  Streaming: {'ON' if ctx.streaming else 'OFF'}")
        print(f"  Thinking: {'ON' if ctx.thinking_enabled else 'OFF'}")
        if ctx.session_id:
            print(f"  Session: {ctx.session_id}")
    
    @staticmethod
    def log_request_complete(ctx: RequestContext):
        """Log when request completes"""
        if ctx.error:
            print(f"  [FAILED] {ctx.error} ({ctx.elapsed_time:.1f}s)")
        else:
            est_mark = " (est)" if ctx.estimated else ""
            print(f"  [SUCCESS] {len(ctx.response_text)} chars ({ctx.elapsed_time:.1f}s)")
            print(f"  📊 Tokens: {ctx.input_tokens} in | {ctx.output_tokens} out | {ctx.total_tokens} total{est_mark}")
        print(f"{'='*60}\n")
    
    @staticmethod
    def execute_streaming(ctx: RequestContext, 
                          session,
                          config: Dict,
                          ai_params: Dict, 
                          key_managers: Dict,
                          callbacks: StreamCallback) -> RequestContext:
        """Execute streaming API request with logging"""
        from .api_client import call_api_chat_stream
        
        RequestPipeline.log_request_start(ctx)
        start_time = time.time()
        
        # Wrap the user's callback to capture data
        def stream_wrapper(data_type, content):
            if data_type == "text":
                ctx.response_text += content
                if callbacks.on_text:
                    callbacks.on_text(content)
            elif data_type == "thinking":
                ctx.reasoning_text += content
                if callbacks.on_thinking:
                    callbacks.on_thinking(content)
            elif data_type == "usage":
                ctx.input_tokens = content.get("prompt_tokens", 0)
                ctx.output_tokens = content.get("completion_tokens", 0)
                ctx.total_tokens = content.get("total_tokens", 0)
                ctx.estimated = content.get("estimated", False)
                if callbacks.on_usage:
                    callbacks.on_usage(content)
            elif data_type == "done":
                if callbacks.on_done:
                    callbacks.on_done()
            elif data_type == "error":
                ctx.error = content
                if callbacks.on_error:
                    callbacks.on_error(content)
        
        # Execute the actual API call
        text, reasoning, usage, error = call_api_chat_stream(
            session, config, ai_params, key_managers, stream_wrapper
        )
        
        ctx.elapsed_time = time.time() - start_time
        if error:
            ctx.error = error
        
        RequestPipeline.log_request_complete(ctx)
        return ctx
    
    @staticmethod
    def execute_simple(ctx: RequestContext,
                       messages: list,
                       config: Dict,
                       ai_params: Dict,
                       key_managers: Dict) -> RequestContext:
        """Execute non-streaming API request with logging"""
        from .api_client import call_api_with_retry, estimate_message_tokens, estimate_tokens
        
        RequestPipeline.log_request_start(ctx)
        start_time = time.time()
        
        text, error = call_api_with_retry(
            provider=ctx.provider,
            messages=messages,
            model_override=ctx.model,
            config=config,
            ai_params=ai_params,
            key_managers=key_managers
        )
        
        ctx.elapsed_time = time.time() - start_time
        
        if error:
            ctx.error = error
        else:
            ctx.response_text = text or ""
            # Estimate tokens
            ctx.input_tokens = estimate_message_tokens(messages)
            ctx.output_tokens = estimate_tokens(text or "")
            ctx.total_tokens = ctx.input_tokens + ctx.output_tokens
            ctx.estimated = True
        
        RequestPipeline.log_request_complete(ctx)
        return ctx