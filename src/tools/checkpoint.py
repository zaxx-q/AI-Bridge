#!/usr/bin/env python3
"""
Checkpoint Manager - Save and resume batch processing state

Provides:
- Checkpoint creation and persistence
- Resume from saved state
- Progress tracking across sessions
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any


@dataclass
class FileProcessorCheckpoint:
    """
    Checkpoint state for File Processor.
    
    Stores all information needed to resume a batch processing session.
    """
    
    # Session identification
    session_id: str
    created_at: str
    updated_at: str
    
    # Input configuration
    input_path: str
    input_files: List[str]  # Full list of file paths to process
    prompt_key: str  # Name of the prompt used
    prompt_text: str  # Actual prompt content
    
    # Output configuration
    output_mode: str  # "individual" or "combined"
    output_path: str  # Output directory
    naming_template: str  # File naming template
    output_extension: str  # Output file extension
    
    # Execution settings
    provider: str
    model: str
    delay_between_requests: float
    
    # Progress tracking
    completed_files: List[str] = field(default_factory=list)
    failed_files: List[Dict[str, str]] = field(default_factory=list)  # {"path": str, "error": str}
    current_index: int = 0
    
    # For combined output mode - accumulated content
    combined_output_content: str = ""
    
    @property
    def remaining_files(self) -> List[str]:
        """Get list of files not yet processed"""
        completed_set = set(self.completed_files)
        failed_set = {f["path"] for f in self.failed_files}
        processed = completed_set | failed_set
        return [f for f in self.input_files if f not in processed]
    
    @property
    def progress_percent(self) -> float:
        """Get progress as percentage"""
        if not self.input_files:
            return 0.0
        processed = len(self.completed_files) + len(self.failed_files)
        return (processed / len(self.input_files)) * 100
    
    @property
    def is_complete(self) -> bool:
        """Check if all files have been processed"""
        return len(self.remaining_files) == 0
    
    def mark_completed(self, file_path: str):
        """Mark a file as successfully completed"""
        if file_path not in self.completed_files:
            self.completed_files.append(file_path)
        self.current_index = len(self.completed_files) + len(self.failed_files)
        self.updated_at = datetime.now().isoformat()
    
    def mark_failed(self, file_path: str, error: str):
        """Mark a file as failed with error"""
        # Remove from completed if somehow there
        if file_path in self.completed_files:
            self.completed_files.remove(file_path)
        
        # Add to failed (update if already there)
        for i, f in enumerate(self.failed_files):
            if f["path"] == file_path:
                self.failed_files[i]["error"] = error
                break
        else:
            self.failed_files.append({"path": file_path, "error": error})
        
        self.current_index = len(self.completed_files) + len(self.failed_files)
        self.updated_at = datetime.now().isoformat()
    
    def append_combined_content(self, file_path: str, content: str, separator: str = None):
        """Append content to combined output (for combined mode)"""
        if separator is None:
            separator = f"\n\n---\n## {Path(file_path).name}\n\n"
        
        if self.combined_output_content:
            self.combined_output_content += separator
        self.combined_output_content += content
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileProcessorCheckpoint":
        """Create from dictionary (filters out unknown arguments for compatibility)"""
        import inspect
        sig = inspect.signature(cls)
        valid_args = {k: v for k, v in data.items() if k in sig.parameters}
        return cls(**valid_args)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of checkpoint state"""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "prompt_key": self.prompt_key,
            "total_files": len(self.input_files),
            "completed": len(self.completed_files),
            "failed": len(self.failed_files),
            "remaining": len(self.remaining_files),
            "progress_percent": self.progress_percent,
            "output_path": self.output_path,
            "provider": self.provider,
            "model": self.model,
        }


class CheckpointManager:
    """
    Manage checkpoint persistence for File Processor.
    
    Features:
    - Save/load checkpoint to JSON file
    - Create new checkpoints
    - Clear completed checkpoints
    - Query checkpoint existence and validity
    """
    
    DEFAULT_CHECKPOINT_FILE = ".file_processor_checkpoint.json"
    
    def __init__(self, checkpoint_file: str = None, checkpoint_dir: Path = None):
        """
        Initialize CheckpointManager.
        
        Args:
            checkpoint_file: Checkpoint filename (default: .file_processor_checkpoint.json)
            checkpoint_dir: Directory for checkpoint file (default: current directory)
        """
        self.checkpoint_file = checkpoint_file or self.DEFAULT_CHECKPOINT_FILE
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else Path(".")
    
    @property
    def checkpoint_path(self) -> Path:
        """Get full path to checkpoint file"""
        return self.checkpoint_dir / self.checkpoint_file
    
    def exists(self) -> bool:
        """Check if a checkpoint file exists"""
        return self.checkpoint_path.exists()
    
    def load(self) -> Optional[FileProcessorCheckpoint]:
        """
        Load checkpoint from file.
        
        Returns:
            FileProcessorCheckpoint if exists and valid, None otherwise
        """
        if not self.exists():
            return None
        
        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return FileProcessorCheckpoint.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"[Warning] Failed to load checkpoint: {e}")
            return None
    
    def save(self, checkpoint: FileProcessorCheckpoint):
        """
        Save checkpoint to file.
        
        Args:
            checkpoint: Checkpoint to save
        """
        checkpoint.updated_at = datetime.now().isoformat()
        
        # Ensure directory exists
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        with open(self.checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint.to_dict(), f, indent=2, ensure_ascii=False)
    
    def clear(self):
        """Remove checkpoint file"""
        if self.exists():
            self.checkpoint_path.unlink()
    
    def create(
        self,
        input_path: str,
        input_files: List[str],
        prompt_key: str,
        prompt_text: str,
        output_mode: str,
        output_path: str,
        naming_template: str,
        output_extension: str,
        provider: str,
        model: str,
        delay: float
    ) -> FileProcessorCheckpoint:
        """
        Create a new checkpoint.
        
        Args:
            input_path: Input file or directory path
            input_files: List of file paths to process
            prompt_key: Prompt name/key
            prompt_text: Actual prompt content
            output_mode: "individual" or "combined"
            output_path: Output directory
            naming_template: File naming template
            output_extension: Output file extension
            provider: AI provider name
            model: Model name
            delay: Delay between requests in seconds
        
        Returns:
            New FileProcessorCheckpoint
        """
        now = datetime.now().isoformat()
        
        return FileProcessorCheckpoint(
            session_id=str(uuid.uuid4())[:8],
            created_at=now,
            updated_at=now,
            input_path=input_path,
            input_files=input_files,
            prompt_key=prompt_key,
            prompt_text=prompt_text,
            output_mode=output_mode,
            output_path=output_path,
            naming_template=naming_template,
            output_extension=output_extension,
            provider=provider,
            model=model,
            delay_between_requests=delay,
            completed_files=[],
            failed_files=[],
            current_index=0,
            combined_output_content=""
        )
    
    def get_summary(self) -> Optional[Dict[str, Any]]:
        """
        Get summary of existing checkpoint without loading full data.
        
        Returns:
            Summary dict if checkpoint exists, None otherwise
        """
        checkpoint = self.load()
        if checkpoint:
            return checkpoint.get_summary()
        return None
    
    def can_resume(self, input_path: str = None) -> bool:
        """
        Check if checkpoint can be resumed.
        
        Args:
            input_path: Optional - verify checkpoint is for this input path
        
        Returns:
            True if checkpoint exists and is resumable
        """
        checkpoint = self.load()
        if not checkpoint:
            return False
        
        if checkpoint.is_complete:
            return False
        
        if input_path and checkpoint.input_path != input_path:
            return False
        
        return True