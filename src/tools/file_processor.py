#!/usr/bin/env python3
"""
File Processor Tool - Interactive terminal workflow for batch file processing

Provides:
- Interactive wizard for file/folder selection
- Prompt selection (tool prompts + endpoint prompts)
- Output configuration (individual/combined, naming, destination)
- Progress display with pause/stop/resume
- Checkpoint persistence
- Large file handling (Files API or FFmpeg chunking)
"""

import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple

from .base import BaseTool, ToolResult, ToolStatus
from .file_handler import FileHandler, FileInfo, ScanResult
from .checkpoint import CheckpointManager, FileProcessorCheckpoint
from .config import (
    load_tools_config,
    get_file_processor_prompts,
    get_prompt_by_key,
    get_setting,
    list_available_prompts,
    resolve_endpoint_prompt,
)
from .audio_processor import (
    AudioProcessor,
    AudioEffect,
    AudioPreset,
    Intensity,
    OutputOptimization,
    SAMPLE_RATE_OPTIONS,
    BITRATE_OPTIONS,
    check_ffmpeg_available,
    needs_chunking,
    is_audio_file,
    get_preset,
    get_all_presets,
    get_presets_by_category,
    TARGET_CHUNK_SIZE_BYTES,
)

# Import console utilities
from src.console import console, Panel, Table, print_panel, print_success, print_error, print_warning, print_info, HAVE_RICH

# Maximum inline file size (15 MB)
MAX_INLINE_SIZE = 15 * 1024 * 1024


# Large file handling modes
LARGE_FILE_MODE_FILES_API = "files_api"
LARGE_FILE_MODE_CHUNKING = "chunking"
LARGE_FILE_MODE_SKIP = "skip"


class FileProcessor(BaseTool):
    """
    File Processor Tool - Process files with AI prompts.
    
    Supports:
    - Image files (via vision API)
    - Audio files (via audio API)
    - Text/code files (via text API)
    - Batch processing with progress
    - Checkpoint/resume for interrupted sessions
    - Large file handling (Files API or FFmpeg chunking)
    """
    
    def __init__(self, config: Dict[str, Any] = None, endpoints: Dict[str, str] = None):
        """
        Initialize File Processor.
        
        Args:
            config: Main application config (from web_server.CONFIG)
            endpoints: Endpoint prompts from config.ini
        """
        super().__init__("file_processor", config)
        self.endpoints = endpoints or {}
        self.tools_config = load_tools_config()
        self.file_handler = FileHandler()
        self.checkpoint_manager = CheckpointManager()
        self.audio_processor = AudioProcessor()
        
        # Processing state
        self._current_checkpoint: Optional[FileProcessorCheckpoint] = None
        self._processing_callback: Optional[Callable] = None
        self._large_file_mode: Dict[str, str] = {}  # file_path -> mode
        self._audio_preprocessing: Optional[Dict[str, Any]] = None  # Audio preprocessing settings
    
    def run_interactive(self) -> ToolResult:
        """
        Run the File Processor interactively in terminal.
        
        Returns:
            ToolResult with processing outcome
        """
        try:
            # Check for existing checkpoint
            if self.checkpoint_manager.exists():
                resume = self._prompt_resume_checkpoint()
                if resume is None:
                    return ToolResult(success=False, message="Cancelled")
                elif resume:
                    return self._resume_from_checkpoint()
                else:
                    self.checkpoint_manager.clear()
            
            # Step 1: Input selection
            scan_result = self._step_input_selection()
            if scan_result is None:
                return ToolResult(success=False, message="Cancelled")
            
            # Step 1.5: Audio Effects (if audio files detected)
            if "audio" in scan_result.by_type:
                self._audio_preprocessing = self._step_audio_preprocessing(scan_result)
                # None means cancelled, empty dict means skip preprocessing
                if self._audio_preprocessing is None:
                    return ToolResult(success=False, message="Cancelled")
                
                # Step 1.6: Audio Optimization (after effects)
                self._audio_preprocessing = self._step_audio_optimization(scan_result, self._audio_preprocessing)
                if self._audio_preprocessing is None:
                    return ToolResult(success=False, message="Cancelled")
            
            # Step 2: Prompt selection
            prompt_key, prompt_text = self._step_prompt_selection(scan_result)
            if prompt_key is None:
                return ToolResult(success=False, message="Cancelled")
            
            # Step 3: Output configuration
            output_config = self._step_output_configuration(scan_result, prompt_key)
            if output_config is None:
                return ToolResult(success=False, message="Cancelled")
            
            # Step 4: Execution settings
            exec_settings = self._step_execution_settings()
            if exec_settings is None:
                return ToolResult(success=False, message="Cancelled")
            
            # Create checkpoint
            input_files = [str(f.path) for f in scan_result.files]
            self._current_checkpoint = self.checkpoint_manager.create(
                input_path=str(scan_result.input_path),
                input_files=input_files,
                prompt_key=prompt_key,
                prompt_text=prompt_text,
                output_mode=output_config["mode"],
                output_path=output_config["path"],
                naming_template=output_config["naming"],
                output_extension=output_config["extension"],
                provider=exec_settings["provider"],
                model=exec_settings["model"],
                delay=exec_settings["delay"]
            )
            
            # Step 5: Execute processing
            return self._execute_processing()
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            if self._current_checkpoint:
                self.checkpoint_manager.save(self._current_checkpoint)
                print("💾 Progress saved. Resume with [X] Tools → File Processor")
            return ToolResult(success=False, message="Interrupted")
    
    def run_batch(
        self,
        input_path: str,
        prompt: str,
        output_config: Dict[str, Any],
        **kwargs
    ) -> ToolResult:
        """
        Run in batch mode (non-interactive).
        
        Args:
            input_path: Path to input file or folder
            prompt: Processing prompt
            output_config: Output configuration dict
            **kwargs: Additional options (provider, model, delay)
        
        Returns:
            ToolResult
        """
        # Scan input
        path = Path(input_path)
        scan_result = self.file_handler.scan(path, recursive=kwargs.get("recursive", False))
        
        if not scan_result.files:
            return ToolResult(success=False, message="No files found")
        
        # Create checkpoint
        input_files = [str(f.path) for f in scan_result.files]
        self._current_checkpoint = self.checkpoint_manager.create(
            input_path=input_path,
            input_files=input_files,
            prompt_key="batch",
            prompt_text=prompt,
            output_mode=output_config.get("mode", "individual"),
            output_path=output_config.get("path", str(path.parent)),
            naming_template=output_config.get("naming", "{filename}_processed"),
            output_extension=output_config.get("extension", ".txt"),
            provider=kwargs.get("provider", "google"),
            model=kwargs.get("model", ""),
            delay=kwargs.get("delay", 1.0)
        )
        
        return self._execute_processing(interactive=False)
    
    # ─────────────────────────────────────────────────────────────────
    # STEP 1: Input Selection
    # ─────────────────────────────────────────────────────────────────
    
    def _step_input_selection(self) -> Optional[ScanResult]:
        """
        Step 1: Get input file or folder path from user.
        
        Returns:
            ScanResult or None if cancelled
        """
        self._print_header("📁 FILE PROCESSOR - Step 1: Input Selection")
        
        while True:
            print("\nEnter path to file or folder (or 'q' to cancel):")
            try:
                path_str = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                return None
            
            if path_str.lower() == 'q':
                return None
            
            if not path_str:
                print_warning("Please enter a path")
                continue
            
            # Handle quoted paths
            if path_str.startswith('"') and path_str.endswith('"'):
                path_str = path_str[1:-1]
            
            path = Path(path_str)
            
            if not path.exists():
                print_error(f"Path does not exist: {path}")
                continue
            
            # Ask about recursive scanning for directories
            recursive = False
            if path.is_dir():
                try:
                    recursive_input = input("Scan subdirectories? [y/N]: ").strip().lower()
                    recursive = recursive_input == 'y'
                except (EOFError, KeyboardInterrupt):
                    return None
            
            # Scan the path
            print("\n🔍 Scanning...")
            scan_result = self.file_handler.scan(path, recursive=recursive)
            
            if not scan_result.files:
                print_error("No supported files found")
                continue
            
            # Display results
            self._display_scan_results(scan_result)
            
            # Handle mixed file types warning
            if scan_result.has_mixed_types:
                warn_setting = get_setting(self.tools_config, "warn_on_mixed_file_types", True)
                allow_setting = get_setting(self.tools_config, "allow_mixed_file_types", False)
                
                if warn_setting:
                    print_warning("⚠️  Multiple file types detected!")
                    
                    if not allow_setting:
                        print("\nOptions:")
                        print("  [1] Process all files anyway")
                        print("  [2] Filter by type")
                        print("  [Q] Cancel")
                        
                        try:
                            choice = input("\nChoice: ").strip().lower()
                        except (EOFError, KeyboardInterrupt):
                            return None
                        
                        if choice == 'q':
                            return None
                        elif choice == '2':
                            scan_result = self._filter_by_type(scan_result)
                            if scan_result is None:
                                return None
            
            # Confirm
            try:
                confirm = input(f"\nProceed with {len(scan_result.files)} files? [Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None
            
            if confirm == 'n':
                continue
            
            return scan_result
    
    def _display_scan_results(self, scan_result: ScanResult):
        """Display scan results summary"""
        if HAVE_RICH:
            table = Table(show_header=True, box=None)
            table.add_column("Type", style="bold")
            table.add_column("Count", justify="right")
            table.add_column("Extensions", style="dim")
            
            for file_type, files in scan_result.by_type.items():
                extensions = set(f.extension for f in files)
                table.add_row(
                    file_type,
                    str(len(files)),
                    ", ".join(sorted(extensions))
                )
            
            console.print(f"\n📊 Found {scan_result.total_count} files:")
            console.print(table)
        else:
            print(f"\n📊 Found {scan_result.total_count} files:")
            for file_type, files in scan_result.by_type.items():
                extensions = set(f.extension for f in files)
                print(f"   • {len(files)} {file_type} ({', '.join(sorted(extensions))})")
    
    def _filter_by_type(self, scan_result: ScanResult) -> Optional[ScanResult]:
        """Allow user to filter files by type"""
        print("\nSelect file type to process:")
        types = list(scan_result.by_type.keys())
        for i, ft in enumerate(types, 1):
            count = len(scan_result.by_type[ft])
            print(f"  [{i}] {ft} ({count} files)")
        
        try:
            choice = input("\nChoice: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(types):
                selected_type = types[idx]
                # Create filtered result
                filtered = ScanResult(
                    input_path=scan_result.input_path,
                    files=scan_result.by_type[selected_type],
                    by_type={selected_type: scan_result.by_type[selected_type]},
                    warnings=[]
                )
                print(f"\n✅ Filtered to {len(filtered.files)} {selected_type} files")
                return filtered
        except (ValueError, IndexError, EOFError, KeyboardInterrupt):
            pass
        
        return None
    
    # ─────────────────────────────────────────────────────────────────
    # STEP 1.5: Audio Effects / Cleanup
    # ─────────────────────────────────────────────────────────────────
    
    def _step_audio_preprocessing(self, scan_result: ScanResult) -> Optional[Dict[str, Any]]:
        """
        Optional step: Configure audio effects and cleanup.
        
        Args:
            scan_result: Scan result with audio files
            
        Returns:
            Preprocessing config dict (empty if skip), None if cancelled
        """
        audio_files = scan_result.by_type.get("audio", [])
        audio_count = len(audio_files)
        
        if not self.audio_processor.is_available():
            print_warning("\n⚠️ FFmpeg not available - audio preprocessing disabled")
            return {}
        
        # Get a sample audio file for preview
        sample_audio = audio_files[0].path if audio_files else None
        has_ffplay = self.audio_processor.is_ffplay_available()
        
        # Current settings (can be adjusted in the loop)
        current_config: Dict[str, Any] = {}
        
        while True:
            print(f"\n🎵 Audio Effects & Cleanup ({audio_count} file(s))")
            print("─" * 50)
            
            # Show current settings
            if current_config:
                self._display_preprocessing_settings(current_config)
            else:
                print("  Current: No effects (Original audio)")
            
            print("\n📋 Quick Options:")
            print("  [1] No Effects - Skip to optimization")
            print("  [2] Normalize - Auto-adjust to optimal level (EBU R128)")
            
            print("\n🎤 Voice Enhancement Presets:")
            print("  [3] Voice Clarity - Enhance speech intelligibility")
            print("  [4] Noise Reduction - Remove background noise")
            print("  [5] Podcast Ready - Broadcast-quality voice")
            print("  [6] Phone Recording - Enhance low-quality audio")
            print("  [7] More presets...")
            
            print("\n🔧 Advanced:")
            print("  [A] Advanced mode - Custom effect chains")
            
            if has_ffplay and sample_audio:
                print("\n  [P] Preview audio - Listen to sample with current settings")
            elif not has_ffplay:
                print("\n  [P] Preview audio - (FFplay not available)")
            
            if current_config:
                print("  [C] Continue")
            print("  [Q] Cancel")
            
            try:
                choice = input("\nChoice: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None
            
            if choice == 'q':
                return None
            
            if choice == 'c' and current_config:
                return current_config
            
            if choice == '1':
                return {}
            
            if choice == '2':
                # Normalize only
                current_config = {"type": "normalize"}
                print("✅ Will normalize audio to optimal level (EBU R128)")
                continue
            
            # Voice enhancement presets
            preset_map = {
                '3': 'voice_clarity',
                '4': 'noise_reduction',
                '5': 'podcast',
                '6': 'phone_recording',
            }
            
            if choice in preset_map:
                preset_id = preset_map[choice]
                config = self._select_preset_intensity(preset_id)
                if config is None:
                    return None
                if config:
                    current_config = config
                continue
            
            if choice == '7':
                # Show all presets
                config = self._show_all_presets()
                if config is None:
                    return None
                if config:
                    current_config = config
                continue
            
            if choice == 'a':
                # Advanced mode
                config = self._advanced_effect_mode(sample_audio, has_ffplay)
                if config is None:
                    return None
                if config:
                    current_config = config
                continue
            
            if choice == 'p' and has_ffplay and sample_audio:
                # Preview with current settings
                self._preview_audio_settings(sample_audio, current_config)
                continue
            
            # If no valid choice and we have settings, continue with them
            if current_config:
                print_info("Press [C] to continue with current settings or choose an option")
    
    def _select_preset_intensity(self, preset_id: str) -> Optional[Dict[str, Any]]:
        """
        Select intensity level for a preset.
        
        Args:
            preset_id: Preset ID to configure
            
        Returns:
            Config dict, empty to skip, or None if cancelled
        """
        preset = get_preset(preset_id)
        if not preset:
            print_error(f"Preset not found: {preset_id}")
            return {}
        
        print(f"\n{preset.name}")
        print(f"  {preset.description}")
        print("\nIntensity:")
        print("  [1] Low - Subtle effect")
        print("  [2] Medium - Balanced (recommended)")
        print("  [3] High - Strong effect")
        print("  [B] Back")
        
        try:
            choice = input("\nChoice [2]: ").strip() or "2"
        except (EOFError, KeyboardInterrupt):
            return None
        
        if choice.lower() == 'b':
            return {}
        
        intensity_map = {
            '1': Intensity.LOW,
            '2': Intensity.MEDIUM,
            '3': Intensity.HIGH,
        }
        
        intensity = intensity_map.get(choice, Intensity.MEDIUM)
        
        print(f"✅ Will apply {preset.name} ({intensity.value})")
        
        return {
            "type": "preset",
            "preset_id": preset_id,
            "intensity": intensity.value
        }
    
    def _show_all_presets(self) -> Optional[Dict[str, Any]]:
        """
        Show all available presets organized by category.
        
        Returns:
            Config dict, empty to go back, or None if cancelled
        """
        all_presets = get_all_presets()
        
        # Group by category
        categories = {}
        for preset in all_presets:
            cat = preset.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(preset)
        
        print("\n📋 All Voice Enhancement Presets")
        print("─" * 50)
        
        idx = 1
        preset_list = []
        
        for cat_name, presets in categories.items():
            cat_icon = {"voice": "🎤", "cleanup": "🔇", "volume": "🔊"}.get(cat_name, "📌")
            print(f"\n{cat_icon} {cat_name.upper()}")
            
            for preset in presets:
                print(f"  [{idx}] {preset.name}")
                print(f"       {preset.description}")
                preset_list.append(preset)
                idx += 1
        
        print("\n  [B] Back")
        
        try:
            choice = input("\nSelect preset: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        
        if choice == 'b':
            return {}
        
        try:
            selected_idx = int(choice) - 1
            if 0 <= selected_idx < len(preset_list):
                return self._select_preset_intensity(preset_list[selected_idx].id)
        except ValueError:
            pass
        
        print_warning("Invalid selection")
        return {}
    
    def _advanced_effect_mode(self, sample_audio: Optional[Path], has_ffplay: bool) -> Optional[Dict[str, Any]]:
        """
        Advanced mode for custom effect chain building.
        
        Args:
            sample_audio: Path to sample file for preview
            has_ffplay: Whether FFplay is available
            
        Returns:
            Config dict, empty to go back, or None if cancelled
        """
        print("\n🔧 Advanced Audio Effects Mode")
        print("─" * 50)
        
        # Current effect chain
        effects: List[AudioEffect] = []
        
        # Available individual effects
        available_effects = {
            '1': ("highpass", "Remove low frequencies (rumble)", {"f": 80}),
            '2': ("lowpass", "Remove high frequencies (hiss)", {"f": 12000}),
            '3': ("afftdn", "FFT noise reduction", {"nr": 15, "nf": -40, "tn": 1}),
            '4': ("speechnorm", "Speech normalization", {"e": 12.5, "r": 0.0001, "l": 1}),
            '5': ("dynaudnorm", "Dynamic range normalizer", {"f": 300, "g": 10, "p": 0.9}),
            '6': ("loudnorm", "EBU R128 loudness normalization", {"I": -16, "LRA": 11, "TP": -1.5}),
            '7': ("equalizer", "Boost presence (3kHz)", {"f": 3000, "t": "q", "w": 1.5, "g": 3}),
            '8': ("compand", "Voice compression", {"attacks": 0.1, "decays": 0.3, "points": "-80/-80|-45/-45|-30/-30|-20/-25|0/-10"}),
        }
        
        while True:
            print("\nCurrent chain:", end=" ")
            if effects:
                print(", ".join(e.name for e in effects))
            else:
                print("(empty)")
            
            print("\nAdd effect:")
            for key, (name, desc, _) in available_effects.items():
                print(f"  [{key}] {name} - {desc}")
            
            print("\n  [R] Remove last effect")
            print("  [X] Clear all effects")
            if has_ffplay and sample_audio and effects:
                print("  [P] Preview current chain")
            print("  [D] Done - use current chain")
            print("  [B] Back (discard changes)")
            
            try:
                choice = input("\nChoice: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None
            
            if choice == 'b':
                return {}
            
            if choice == 'd':
                if effects:
                    print(f"✅ Will apply custom chain: {', '.join(e.name for e in effects)}")
                    return {
                        "type": "custom",
                        "effects": [{"name": e.name, "params": e.params} for e in effects]
                    }
                else:
                    print_warning("No effects in chain")
                    continue
            
            if choice == 'r' and effects:
                removed = effects.pop()
                print(f"Removed: {removed.name}")
                continue
            
            if choice == 'x':
                effects = []
                print("Cleared all effects")
                continue
            
            if choice == 'p' and has_ffplay and sample_audio and effects:
                self.audio_processor.preview_effects(
                    sample_audio,
                    effects,
                    duration_seconds=10.0
                )
                continue
            
            if choice in available_effects:
                name, desc, default_params = available_effects[choice]
                
                # For some effects, allow parameter customization
                params = self._customize_effect_params(name, default_params)
                if params is None:
                    continue
                
                effects.append(AudioEffect(name, params, desc))
                print(f"Added: {name}")
                continue
        
        return {}
    
    def _customize_effect_params(self, effect_name: str, default_params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Allow user to customize effect parameters.
        
        Args:
            effect_name: Name of the effect
            default_params: Default parameters
            
        Returns:
            Customized parameters or None to cancel
        """
        # For now, show simple customization for common effects
        if effect_name == "highpass":
            print(f"  Cutoff frequency [80] Hz: ", end="")
            try:
                val = input().strip()
                if val:
                    return {"f": int(val)}
            except (ValueError, EOFError, KeyboardInterrupt):
                pass
            return default_params
        
        if effect_name == "lowpass":
            print(f"  Cutoff frequency [12000] Hz: ", end="")
            try:
                val = input().strip()
                if val:
                    return {"f": int(val)}
            except (ValueError, EOFError, KeyboardInterrupt):
                pass
            return default_params
        
        if effect_name == "afftdn":
            print(f"  Noise reduction strength (0-97) [15]: ", end="")
            try:
                val = input().strip()
                if val:
                    nr = max(0, min(97, int(val)))
                    return {"nr": nr, "nf": -40, "tn": 1}
            except (ValueError, EOFError, KeyboardInterrupt):
                pass
            return default_params
        
        if effect_name == "equalizer":
            print(f"  Center frequency [3000] Hz: ", end="")
            try:
                freq = input().strip()
                print(f"  Gain [-12 to +12] [3] dB: ", end="")
                gain = input().strip()
                
                f = int(freq) if freq else 3000
                g = float(gain) if gain else 3
                return {"f": f, "t": "q", "w": 1.5, "g": g}
            except (ValueError, EOFError, KeyboardInterrupt):
                pass
            return default_params
        
        # Use defaults for other effects
        return default_params
    
    def _step_audio_optimization(self, scan_result: ScanResult, current_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Step 1.6: Configure file size optimization.
        
        Args:
            scan_result: Scan result with audio files
            current_config: Existing config from Step 1.5 (effects)
            
        Returns:
            Updated config dict or None if cancelled
        """
        audio_files = scan_result.by_type.get("audio", [])
        
        # Sample for defaults
        sample_audio = audio_files[0].path if audio_files else None
        channel_count = 2
        if sample_audio:
             audio_info = self.audio_processor.get_audio_info(sample_audio)
             if audio_info and audio_info.channels:
                 channel_count = audio_info.channels
        
        while True:
            # Check current optimization status
            opt_config = current_config.get("optimization", {})
            
            print(f"\n📦 Audio File Optimization")
            print("─" * 50)
            
            # Display effects summary if present
            if current_config.get("type"):
                self._display_preprocessing_settings(current_config, label="Effects")
                
            # Display current optimization
            if opt_config:
                self._display_optimization_settings(opt_config)
            else:
                print("  Optimization: None (Original quality/size)")

            print("\n📋 Options:")
            print("  [1] Quick presets (Voice, Podcast, etc.)")
            print("  [2] Custom settings (Mono, Sample Rate, Bitrate)")
            print("  [3] Skip optimization (Keep original)")
            
            print("\n  [E] Estimate file size & check chunking")
            
            print("\n  [C] Continue")
            print("  [Q] Cancel")
            
            try:
                choice = input("\nChoice: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None
                
            if choice == 'q':
                return None
            
            if choice == 'c' or (choice == '3' and not opt_config):
                return current_config
            
            if choice == '1':
                # Quick presets
                presets_config = self._show_optimization_presets(channel_count)
                if presets_config == "custom":
                     # Go to custom
                     updated = self._step_file_optimization(audio_files, current_config)
                     if updated:
                         current_config = updated
                elif presets_config:
                    current_config["optimization"] = presets_config
                elif presets_config == {}: # Skip/Clear
                    current_config.pop("optimization", None)
                continue
                
            if choice == '2':
                # Custom settings
                updated = self._step_file_optimization(audio_files, current_config)
                if updated:
                    current_config = updated
                continue
                
            if choice == '3':
                # Clear optimization
                current_config.pop("optimization", None)
                print("✅ Optimization cleared")
                continue
                
            if choice == 'e':
                self._preview_file_size(audio_files, current_config)
                continue

    def _display_optimization_settings(self, opt_config: Dict[str, Any]):
        """Display current optimization settings"""
        parts = []
        if opt_config.get("convert_to_mono"):
            parts.append("Mono")
        if opt_config.get("sample_rate"):
            parts.append(f"{opt_config['sample_rate']}Hz")
        if opt_config.get("bitrate_kbps"):
            parts.append(f"{opt_config['bitrate_kbps']}kbps")
            
        print(f"  Optimization: {', '.join(parts)}")

    def _display_preprocessing_settings(self, config: Dict[str, Any], label: str = "Current"):
        """Display current preprocessing settings"""
        preprocess_type = config.get("type", "")
        
        if preprocess_type == "amplify":
            volume = config.get("volume_percent", 100)
            boost = volume - 100
            print(f"  {label}: Amplify by {boost:+d}%")
        
        elif preprocess_type == "normalize":
            print(f"  {label}: Normalize to optimal level (EBU R128)")
        
        elif preprocess_type == "amplify_normalize":
            volume = config.get("volume_percent", 100)
            boost = volume - 100
            print(f"  {label}: Amplify by {boost:+d}% then Normalize")
        
        elif preprocess_type == "preset":
            preset_id = config.get("preset_id", "")
            intensity = config.get("intensity", "medium")
            preset = get_preset(preset_id)
            if preset:
                print(f"  {label}: {preset.name} ({intensity})")
            else:
                print(f"  {label}: Preset {preset_id} ({intensity})")
        
        elif preprocess_type == "custom":
            effects = config.get("effects", [])
            effect_names = [e.get("name", "?") for e in effects]
            print(f"  {label}: Custom chain - {', '.join(effect_names)}")
    
    def _get_amplify_settings(self, with_normalize: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get volume amplification settings from user.
        
        Args:
            with_normalize: If True, include normalization after amplification
            
        Returns:
            Config dict, empty dict to skip, or None if cancelled
        """
        print("\nEnter volume boost percentage:")
        print("  (e.g., 50 for +50%, -20 for -20%, 0 to skip)")
        
        try:
            percent_str = input("> ").strip()
            if not percent_str:
                return {}
            percent = int(percent_str)
        except (EOFError, KeyboardInterrupt):
            return None
        except ValueError:
            print_warning("Invalid percentage")
            return {}
        
        if percent == 0 and not with_normalize:
            return {}
        
        if with_normalize:
            print(f"✅ Will amplify by {percent:+d}% then normalize")
            return {
                "type": "amplify_normalize",
                "volume_percent": 100 + percent
            }
        else:
            print(f"✅ Will amplify volume by {percent:+d}%")
            return {
                "type": "amplify",
                "volume_percent": 100 + percent
            }
    
    def _preview_audio_settings(self, audio_path: Path, config: Dict[str, Any]):
        """
        Preview audio with current preprocessing settings.
        
        Args:
            audio_path: Path to sample audio file
            config: Current preprocessing config
        """
        print(f"\n🎧 Previewing: {audio_path.name}")
        
        # Get preview duration
        print("Preview duration in seconds [10]: ", end="")
        try:
            duration_str = input().strip()
            duration = float(duration_str) if duration_str else 10.0
        except (ValueError, EOFError, KeyboardInterrupt):
            duration = 10.0
        
        preprocess_type = config.get("type", "")
        
        if not preprocess_type:
            # No preprocessing - play original
            print("Playing original audio...")
            self.audio_processor.play_audio(audio_path, duration_seconds=duration)
        
        elif preprocess_type == "amplify":
            volume = config.get("volume_percent", 100)
            print(f"Playing with {volume - 100:+d}% volume...")
            self.audio_processor.preview_with_effects(
                audio_path,
                volume_percent=volume,
                duration_seconds=duration
            )
        
        elif preprocess_type == "normalize":
            print("Playing normalized audio...")
            self.audio_processor.preview_with_effects(
                audio_path,
                normalize=True,
                duration_seconds=duration
            )
        
        elif preprocess_type == "amplify_normalize":
            # For combined, we need to create a temp file
            volume = config.get("volume_percent", 100)
            print(f"Playing with {volume - 100:+d}% volume + normalization...")
            
            # First amplify to temp file, then preview normalized
            result = self.audio_processor.amplify_volume(
                audio_path,
                volume_percent=volume
            )
            
            if result.success and result.output_path:
                try:
                    self.audio_processor.preview_with_effects(
                        result.output_path,
                        normalize=True,
                        duration_seconds=duration
                    )
                finally:
                    result.cleanup()
            else:
                print_error(f"Could not create preview: {result.error}")
        
        elif preprocess_type == "preset":
            # Preview preset
            preset_id = config.get("preset_id", "")
            intensity_str = config.get("intensity", "medium")
            intensity = Intensity(intensity_str)
            
            preset = get_preset(preset_id)
            if preset:
                print(f"Playing with {preset.name} ({intensity_str})...")
                self.audio_processor.preview_preset(
                    audio_path,
                    preset_id,
                    intensity=intensity,
                    duration_seconds=duration
                )
            else:
                print_error(f"Preset not found: {preset_id}")
        
        elif preprocess_type == "custom":
            # Preview custom effects
            effects_config = config.get("effects", [])
            effects = [AudioEffect(e["name"], e.get("params", {})) for e in effects_config]
            
            if effects:
                print(f"Playing with custom effects...")
                self.audio_processor.preview_effects(
                    audio_path,
                    effects,
                    duration_seconds=duration
                )
            else:
                print_error("No effects configured")
        
        print("✅ Preview finished")
    
    def _preview_file_size(
        self,
        audio_files: List[FileInfo],
        current_config: Dict[str, Any]
    ):
        """
        Preview estimated file sizes after applying current settings.
        
        Shows:
        - Original file sizes
        - Estimated sizes after processing
        - Whether files will need chunking
        
        Args:
            audio_files: List of audio files to analyze
            current_config: Current preprocessing/optimization config
        """
        print("\n📊 File Size Estimation")
        print("─" * 60)
        
        # Get optimization settings
        opt_config = current_config.get("optimization", {})
        convert_to_mono = opt_config.get("convert_to_mono", False)
        target_sample_rate = opt_config.get("sample_rate")
        target_bitrate = opt_config.get("bitrate_kbps")
        
        # Get preset/effect info
        preprocess_type = current_config.get("type", "")
        
        # Show settings being applied
        print("\n  Applied settings:")
        if preprocess_type == "preset":
            preset_id = current_config.get("preset_id", "")
            intensity = current_config.get("intensity", "medium")
            preset = get_preset(preset_id)
            if preset:
                print(f"    • Preset: {preset.name} ({intensity})")
        elif preprocess_type == "custom":
            effects = current_config.get("effects", [])
            if effects:
                effect_names = [e.get("name", "?") for e in effects]
                print(f"    • Effects: {', '.join(effect_names)}")
        elif preprocess_type == "normalize":
            print(f"    • Normalize: EBU R128")
        
        if convert_to_mono:
            print(f"    • Channels: Convert to mono")
        if target_sample_rate:
            print(f"    • Sample rate: {target_sample_rate:,} Hz")
        if target_bitrate:
            print(f"    • Bitrate: {target_bitrate} kbps")
        
        if not any([preprocess_type, convert_to_mono, target_sample_rate, target_bitrate]):
            print(f"    • (No changes - original format)")
        
        print()
        
        # Analyze each file (up to 10 for preview)
        files_to_analyze = audio_files[:10]
        total_original = 0
        total_estimated = 0
        files_needing_chunking_before = 0
        files_needing_chunking_after = 0
        
        if HAVE_RICH:
            table = Table(show_header=True, box=None)
            table.add_column("File", style="bold", max_width=30)
            table.add_column("Original", justify="right")
            table.add_column("Estimated", justify="right")
            table.add_column("Reduction", justify="right")
            table.add_column("Chunking", justify="center")
        
        for file_info in files_to_analyze:
            audio_info = self.audio_processor.get_audio_info(file_info.path)
            if not audio_info:
                continue
            
            original_size = audio_info.size_bytes
            total_original += original_size
            
            # Check if original needs chunking
            if original_size > MAX_INLINE_SIZE:
                files_needing_chunking_before += 1
            
            # Estimate new size
            estimated_size = self._estimate_processed_size(
                audio_info,
                convert_to_mono=convert_to_mono,
                target_sample_rate=target_sample_rate,
                target_bitrate=target_bitrate
            )
            total_estimated += estimated_size
            
            # Check if estimated needs chunking
            needs_chunk_after = estimated_size > MAX_INLINE_SIZE
            if needs_chunk_after:
                files_needing_chunking_after += 1
            
            # Format sizes
            orig_str = self._format_size(original_size)
            est_str = self._format_size(estimated_size)
            
            # Calculate reduction
            if original_size > 0:
                reduction = ((original_size - estimated_size) / original_size) * 100
                reduction_str = f"-{reduction:.0f}%" if reduction > 0 else f"+{abs(reduction):.0f}%"
            else:
                reduction_str = "-"
            
            # Chunking indicator
            if original_size > MAX_INLINE_SIZE and not needs_chunk_after:
                chunk_str = "✅ No longer needed"
            elif needs_chunk_after:
                chunk_str = "⚠️ Still needed"
            else:
                chunk_str = "✓"
            
            filename = file_info.path.name
            if len(filename) > 28:
                filename = filename[:25] + "..."
            
            if HAVE_RICH:
                table.add_row(filename, orig_str, est_str, reduction_str, chunk_str)
            else:
                print(f"  {filename:<30} {orig_str:>10} → {est_str:>10} ({reduction_str:>6}) {chunk_str}")
        
        if HAVE_RICH:
            console.print(table)
        
        # Show totals if multiple files
        if len(files_to_analyze) > 1:
            print(f"\n  ─────────────────────────────────────────────────────────")
            total_orig_str = self._format_size(total_original)
            total_est_str = self._format_size(total_estimated)
            
            if total_original > 0:
                total_reduction = ((total_original - total_estimated) / total_original) * 100
                print(f"  Total: {total_orig_str} → {total_est_str} (-{total_reduction:.0f}%)")
            else:
                print(f"  Total: {total_orig_str} → {total_est_str}")
        
        # Show chunking summary
        if files_needing_chunking_before > 0:
            print(f"\n  📦 Chunking Summary:")
            print(f"     Before: {files_needing_chunking_before} file(s) need chunking (>15MB)")
            print(f"     After:  {files_needing_chunking_after} file(s) need chunking")
            
            if files_needing_chunking_after < files_needing_chunking_before:
                avoided = files_needing_chunking_before - files_needing_chunking_after
                print(f"     ✅ {avoided} file(s) no longer need chunking!")
        
        # Show note if more files exist
        if len(audio_files) > 10:
            print(f"\n  (Showing first 10 of {len(audio_files)} files)")
        
        print()
    
    def _estimate_processed_size(
        self,
        audio_info: 'AudioInfo',
        convert_to_mono: bool = False,
        target_sample_rate: Optional[int] = None,
        target_bitrate: Optional[int] = None
    ) -> int:
        """
        Estimate the output file size after processing.
        
        Uses bitrate-based estimation for compressed formats.
        
        Args:
            audio_info: Original audio information
            convert_to_mono: Whether converting to mono
            target_sample_rate: Target sample rate (Hz)
            target_bitrate: Target bitrate (kbps)
            
        Returns:
            Estimated file size in bytes
        """
        duration = audio_info.duration_seconds
        if duration <= 0:
            return audio_info.size_bytes
        
        # Get original characteristics
        orig_channels = audio_info.channels or 2
        orig_sample_rate = audio_info.sample_rate or 44100
        orig_bitrate = audio_info.bitrate_kbps or 128
        
        # Determine output characteristics
        out_channels = 1 if convert_to_mono else orig_channels
        out_sample_rate = target_sample_rate or orig_sample_rate
        out_bitrate = target_bitrate or orig_bitrate
        
        # For compressed formats (MP3, AAC, etc.), size is primarily determined by bitrate
        # Size (bytes) = (bitrate_kbps * 1000 / 8) * duration_seconds
        # But we need to account for:
        # - Mono vs stereo (mono is typically ~50% smaller at same quality)
        # - Sample rate reduction (proportional reduction)
        
        # If we have a target bitrate, use it directly
        if target_bitrate:
            # Bitrate already accounts for channels in lossy formats
            estimated_bytes = (target_bitrate * 1000 / 8) * duration
        else:
            # Estimate based on original bitrate with adjustments
            estimated_bitrate = orig_bitrate
            
            # Adjust for channel change (rough estimate)
            if convert_to_mono and orig_channels > 1:
                # Mono at same quality is roughly 50-60% of stereo size
                estimated_bitrate *= 0.55
            
            # Adjust for sample rate reduction (proportional)
            if target_sample_rate and target_sample_rate < orig_sample_rate:
                sample_rate_ratio = target_sample_rate / orig_sample_rate
                # Lower sample rate allows lower bitrate at same quality
                # But the relationship isn't perfectly linear
                estimated_bitrate *= (0.5 + 0.5 * sample_rate_ratio)
            
            estimated_bytes = (estimated_bitrate * 1000 / 8) * duration
        
        # Add some overhead for container/headers (~2-5%)
        estimated_bytes *= 1.03
        
        return int(estimated_bytes)
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
    
    def _step_file_optimization(self, audio_files: List[FileInfo], current_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        File size optimization step for audio files.
        
        Prompts user for:
        - Mono conversion (if stereo/multichannel)
        - Bitrate optimization
        - Sample rate downsampling
        
        Args:
            audio_files: List of audio files to process
            current_config: Current preprocessing config (will be modified)
            
        Returns:
            Updated config with optimization settings, empty to skip, or None if cancelled
        """
        print("\n📦 File Size Optimization")
        print("─" * 50)
        print("  Optimize output file size for voice/AI processing")
        
        # Sample one audio file to get channel info
        sample_audio = audio_files[0].path if audio_files else None
        channel_count = 2  # Default assumption
        sample_rate = 44100  # Default assumption
        
        if sample_audio:
            audio_info = self.audio_processor.get_audio_info(sample_audio)
            if audio_info:
                channel_count = audio_info.channels or 2
                sample_rate = audio_info.sample_rate or 44100
                duration = audio_info.duration_seconds
                
                print(f"\n  Sample file info:")
                channel_label = 'Mono' if channel_count == 1 else ('Stereo' if channel_count == 2 else f'{channel_count}-channel')
                print(f"    Channels:    {channel_count} ({channel_label})")
                print(f"    Sample rate: {sample_rate:,} Hz")
                if duration:
                    print(f"    Duration:    {duration:.1f}s")
        
        # Initialize optimization settings
        optimization = OutputOptimization()
        
        # Step 1: Mono conversion (only ask if stereo or more)
        if channel_count >= 2:
            print("\n🔊 Channel Conversion:")
            print("  [1] Keep stereo/multichannel as-is")
            print("  [2] Convert to mono (recommended for voice)")
            print("       • Reduces file size by ~50%")
            print("       • Ideal for speech and AI processing")
            
            try:
                mono_choice = input("\nChoice [2]: ").strip() or "2"
            except (EOFError, KeyboardInterrupt):
                return None
            
            optimization.convert_to_mono = mono_choice == "2"
            if optimization.convert_to_mono:
                print("  ✓ Will convert to mono")
        else:
            # Already mono - ensure we keep it mono (never upmix)
            optimization.convert_to_mono = True  # -ac 1 forces mono output
            print("\n🔊 Audio is already mono (will preserve)")
        
        # Step 2: Sample rate
        print("\n📊 Sample Rate:")
        
        # Determine recommended rate based on content type
        if sample_rate > 48000:
            recommended = 48000
            print(f"  Current: {sample_rate:,} Hz (higher than needed for voice)")
        elif sample_rate > 22050:
            recommended = 22050
            print(f"  Current: {sample_rate:,} Hz")
        else:
            recommended = sample_rate
            print(f"  Current: {sample_rate:,} Hz (already optimized)")
        
        print("\n  Options (lower = smaller file, less quality):")
        # SAMPLE_RATE_OPTIONS is a dict {rate: label}
        rate_options = [(r, SAMPLE_RATE_OPTIONS[r]) for r in sorted(SAMPLE_RATE_OPTIONS.keys()) if r <= sample_rate]
        
        for i, (rate, label) in enumerate(rate_options[:5], 1):  # Show up to 5 options
            marker = " ◄ recommended" if rate == recommended else ""
            print(f"    [{i}] {rate:,} Hz - {label}{marker}")
        
        print(f"    [K] Keep original ({sample_rate:,} Hz)")
        
        try:
            rate_choice = input("\nChoice [K]: ").strip().upper() or "K"
        except (EOFError, KeyboardInterrupt):
            return None
        
        if rate_choice != "K":
            try:
                rate_idx = int(rate_choice) - 1
                if 0 <= rate_idx < len(rate_options[:5]):
                    optimization.sample_rate = rate_options[rate_idx][0]
                    print(f"  ✓ Will resample to {optimization.sample_rate:,} Hz")
            except ValueError:
                pass
        
        if not optimization.sample_rate:
            print(f"  ✓ Keeping original sample rate")
        
        # Step 3: Bitrate
        print("\n🎚️ Output Bitrate (for compressed formats):")
        print("  Lower bitrate = smaller file, potential quality loss")
        print("\n  Voice-optimized options:")
        
        # BITRATE_OPTIONS is a dict {bitrate: label}
        bitrate_options = [(b, BITRATE_OPTIONS[b]) for b in sorted(BITRATE_OPTIONS.keys())]
        
        for i, (bitrate, label) in enumerate(bitrate_options[:6], 1):
            marker = ""
            if bitrate == 64:
                marker = " ◄ recommended for voice"
            elif bitrate == 96:
                marker = " ◄ good balance"
            print(f"    [{i}] {bitrate} kbps - {label}{marker}")
        
        print(f"    [K] Keep codec default")
        
        try:
            bitrate_choice = input("\nChoice [3]: ").strip().upper() or "3"  # Default to 64kbps
        except (EOFError, KeyboardInterrupt):
            return None
        
        if bitrate_choice != "K":
            try:
                bitrate_idx = int(bitrate_choice) - 1
                if 0 <= bitrate_idx < len(bitrate_options[:6]):
                    optimization.bitrate_kbps = bitrate_options[bitrate_idx][0]
                    print(f"  ✓ Will encode at {optimization.bitrate_kbps} kbps")
            except ValueError:
                pass
        
        if not optimization.bitrate_kbps:
            print(f"  ✓ Using codec default bitrate")
        
        # Summary
        print("\n📋 Optimization Summary:")
        if optimization.convert_to_mono:
            print("  • Converting to mono")
        if optimization.sample_rate:
            print(f"  • Resampling to {optimization.sample_rate:,} Hz")
        if optimization.bitrate_kbps:
            print(f"  • Bitrate: {optimization.bitrate_kbps} kbps")
        
        if not any([optimization.convert_to_mono and channel_count >= 2,
                    optimization.sample_rate, optimization.bitrate_kbps]):
            print("  (No optimization - keeping original format)")
        
        # Add optimization to config
        current_config["optimization"] = {
            "convert_to_mono": optimization.convert_to_mono,
            "sample_rate": optimization.sample_rate,
            "bitrate_kbps": optimization.bitrate_kbps
        }
        
        return current_config
    
    def _show_optimization_presets(self, channel_count: int) -> Optional[Dict[str, Any]]:
        """
        Show quick optimization presets.
        
        Args:
            channel_count: Current audio channel count
            
        Returns:
            Optimization dict or None if cancelled
        """
        print("\n⚡ Quick Optimization Presets:")
        print("  [1] 🎤 Voice (smallest) - Mono, 16kHz, 32kbps")
        print("       Best for: Speech, podcasts, AI transcription (phone quality)")
        print("  [2] 🎙️ Podcast (balanced) - Mono, 22kHz, 64kbps")
        print("       Best for: High-quality voice, music with speech")
        print("  [3] 🎵 Quality (larger) - Mono, 44.1kHz, 96kbps")
        print("       Best for: Music, audio with effects (preserves fidelity)")
        print("  [4] 📱 Mobile (tiny) - Mono, 16kHz, 32kbps")
        print("       Best for: Maximum compression, exact same as Voice (smallest)")
        print("  [C] Custom settings...")
        print("  [S] Skip optimization")
        
        try:
            choice = input("\nChoice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        
        presets = {
            "1": OutputOptimization.for_voice_small(),
            "2": OutputOptimization.for_voice_balanced(),
            "3": OutputOptimization.for_voice_quality(),
            "4": OutputOptimization(convert_to_mono=True, sample_rate=16000, bitrate_kbps=32),
        }
        
        if choice in presets:
            opt = presets[choice]
            return {
                "convert_to_mono": opt.convert_to_mono,
                "sample_rate": opt.sample_rate,
                "bitrate_kbps": opt.bitrate_kbps
            }
        elif choice == "c":
            return "custom"  # Signal to run full customization
        elif choice == "s":
            return {}
        
        return None
    
    # ─────────────────────────────────────────────────────────────────
    # STEP 2: Prompt Selection
    # ─────────────────────────────────────────────────────────────────
    
    def _step_prompt_selection(self, scan_result: ScanResult) -> tuple[Optional[str], Optional[str]]:
        """
        Step 2: Select processing prompt.
        
        Returns:
            (prompt_key, prompt_text) or (None, None) if cancelled
        """
        self._print_header("📁 FILE PROCESSOR - Step 2: Prompt Selection")
        
        # Get available prompts
        prompts = list_available_prompts(
            self.tools_config,
            self.endpoints if self.endpoints else None
        )
        
        # Organize by source
        tool_prompts = [p for p in prompts if p["source"] == "tool"]
        endpoint_prompts = [p for p in prompts if p["source"] == "endpoint"]
        
        # Display tool prompts
        print("\n📝 Tool Prompts:")
        for i, p in enumerate(tool_prompts, 1):
            requires_input = ""
            if get_prompt_by_key(self.tools_config, p["key"]):
                config = get_prompt_by_key(self.tools_config, p["key"])
                if config.get("requires_input"):
                    requires_input = " [requires input]"
            print(f"  [{i}] {p['icon']} {p['key']}{requires_input}")
            print(f"      {p['description'][:60]}")
        
        # Display endpoint prompts
        if endpoint_prompts:
            print("\n📡 Endpoint Prompts:")
            for i, p in enumerate(endpoint_prompts, len(tool_prompts) + 1):
                print(f"  [{i}] {p['icon']} {p['key'].replace('@endpoint:', '')}")
                print(f"      {p['description'][:60]}")
        
        print("\n  [C] Enter custom prompt")
        print("  [Q] Cancel")
        
        while True:
            try:
                choice = input("\nSelect prompt: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None, None
            
            if choice == 'q':
                return None, None
            
            if choice == 'c':
                # Custom prompt
                print("\nEnter your custom prompt (end with empty line):")
                lines = []
                try:
                    while True:
                        line = input()
                        if not line:
                            break
                        lines.append(line)
                except (EOFError, KeyboardInterrupt):
                    return None, None
                
                if not lines:
                    print_warning("Empty prompt")
                    continue
                
                return "Custom", "\n".join(lines)
            
            try:
                idx = int(choice) - 1
                all_prompts = tool_prompts + endpoint_prompts
                
                if 0 <= idx < len(all_prompts):
                    selected = all_prompts[idx]
                    prompt_key = selected["key"]
                    
                    # Get the actual prompt text
                    if selected["source"] == "endpoint":
                        endpoint_name = prompt_key.replace("@endpoint:", "")
                        prompt_text = self.endpoints.get(endpoint_name, "")
                    else:
                        config = get_prompt_by_key(self.tools_config, prompt_key)
                        if config:
                            prompt_text = config.get("prompt", "")
                            
                            # Handle prompts that require input
                            if config.get("requires_input") or not prompt_text:
                                print(f"\nEnter prompt for '{prompt_key}':")
                                try:
                                    prompt_text = input("> ").strip()
                                except (EOFError, KeyboardInterrupt):
                                    return None, None
                                if not prompt_text:
                                    print_warning("Empty prompt")
                                    continue
                        else:
                            prompt_text = ""
                    
                    if not prompt_text:
                        print_error("Prompt not found")
                        continue
                    
                    print(f"\n✅ Selected: {prompt_key}")
                    return prompt_key, prompt_text
                else:
                    print_warning("Invalid selection")
            except ValueError:
                print_warning("Invalid input")
    
    # ─────────────────────────────────────────────────────────────────
    # STEP 3: Output Configuration
    # ─────────────────────────────────────────────────────────────────
    
    def _step_output_configuration(self, scan_result: ScanResult, prompt_key: str) -> Optional[Dict[str, Any]]:
        """
        Step 3: Configure output settings.
        
        Returns:
            Output config dict or None if cancelled
        """
        self._print_header("📁 FILE PROCESSOR - Step 3: Output Configuration")
        
        # Get prompt config for defaults
        prompt_config = get_prompt_by_key(self.tools_config, prompt_key) or {}
        default_extension = prompt_config.get("output_extension", ".txt")
        default_naming = prompt_config.get("default_naming", "{filename}_processed")
        
        # Output mode - only ask if multiple files
        if scan_result.total_count > 1:
            print("\nOutput Mode:")
            print("  [1] 📄 Individual files - One output per input")
            print("  [2] 📋 Combined file - All outputs in one file")
            
            try:
                mode_choice = input("\nChoice [1]: ").strip() or "1"
            except (EOFError, KeyboardInterrupt):
                return None
            
            output_mode = "combined" if mode_choice == "2" else "individual"
        else:
            # Single file - always individual mode
            output_mode = "individual"
            print("\n📄 Output Mode: Individual (single file)")
        
        # Output destination
        default_output = str(scan_result.input_path if scan_result.input_path.is_dir() else scan_result.input_path.parent)
        print(f"\nOutput destination (Enter for same as input):")
        try:
            output_path = input(f"> [{default_output}]: ").strip() or default_output
        except (EOFError, KeyboardInterrupt):
            return None
        
        # Validate output path
        output_path_obj = Path(output_path)
        if not output_path_obj.exists():
            try:
                create = input(f"Directory doesn't exist. Create? [Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None
            if create != 'n':
                output_path_obj.mkdir(parents=True, exist_ok=True)
            else:
                return None
        
        # Naming template
        if output_mode == "individual":
            print(f"\nNaming template (vars: {{filename}}, {{date}}, {{time}}, {{index}}):")
            try:
                naming = input(f"> [{default_naming}]: ").strip() or default_naming
            except (EOFError, KeyboardInterrupt):
                return None
        else:
            naming = f"batch_output_{{date}}_{{time}}"
        
        # Extension
        print(f"\nOutput extension:")
        try:
            extension = input(f"> [{default_extension}]: ").strip() or default_extension
        except (EOFError, KeyboardInterrupt):
            return None
        
        if not extension.startswith("."):
            extension = "." + extension
        
        config = {
            "mode": output_mode,
            "path": output_path,
            "naming": naming,
            "extension": extension
        }
        
        print(f"\n✅ Output: {output_mode} files to {output_path}")
        return config
    
    # ─────────────────────────────────────────────────────────────────
    # STEP 4: Execution Settings
    # ─────────────────────────────────────────────────────────────────
    
    def _step_execution_settings(self) -> Optional[Dict[str, Any]]:
        """
        Step 4: Configure execution settings (provider, model, etc.)
        
        Returns:
            Settings dict or None if cancelled
        """
        self._print_header("📁 FILE PROCESSOR - Step 4: Execution Settings")
        
        # Import web_server for current config
        from src import web_server
        
        current_provider = web_server.CONFIG.get("default_provider", "google")
        current_model = web_server.CONFIG.get(f"{current_provider}_model", "not set")
        current_thinking = web_server.CONFIG.get("thinking_enabled", False)
        default_delay = get_setting(self.tools_config, "default_delay_between_requests", 1.0)
        
        # Display current settings
        print(f"\nCurrent Settings:")
        print(f"  Provider: {current_provider}")
        print(f"  Model:    {current_model}")
        thinking_status = "ON" if current_thinking else "OFF"
        print(f"  Thinking: {thinking_status} (System Setting)")
        print(f"  Delay:    {default_delay}s between requests")
        
        # Provider selection
        print("\nProvider:")
        providers = list(web_server.KEY_MANAGERS.keys())
        for i, p in enumerate(providers, 1):
            key_count = web_server.KEY_MANAGERS[p].get_key_count()
            marker = " ◄" if p == current_provider else ""
            status = f"({key_count} keys)" if key_count > 0 else "(no keys)"
            print(f"  [{i}] {p} {status}{marker}")
        
        try:
            provider_choice = input(f"\nProvider [{current_provider}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        
        if provider_choice:
            try:
                idx = int(provider_choice) - 1
                if 0 <= idx < len(providers):
                    current_provider = providers[idx]
            except ValueError:
                if provider_choice.lower() in providers:
                    current_provider = provider_choice.lower()
        
        # Model
        current_model = web_server.CONFIG.get(f"{current_provider}_model", "")
        try:
            model_input = input(f"\nModel [{current_model}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        
        if model_input:
            current_model = model_input
            
        # Delay
        try:
            delay_input = input(f"\nDelay between requests (seconds) [{default_delay}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        
        if delay_input:
            try:
                default_delay = float(delay_input)
            except ValueError:
                pass
        
        settings = {
            "provider": current_provider,
            "model": current_model,
            "delay": default_delay
        }
        
        print(f"\n✅ Settings configured")
        return settings
    
    # ─────────────────────────────────────────────────────────────────
    # STEP 5: Execute Processing
    # ─────────────────────────────────────────────────────────────────
    
    def _execute_processing(self, interactive: bool = True) -> ToolResult:
        """
        Execute the actual file processing.
        
        Args:
            interactive: Whether to show interactive progress
        
        Returns:
            ToolResult
        """
        if not self._current_checkpoint:
            return ToolResult(success=False, message="No checkpoint - processing not configured")
        
        cp = self._current_checkpoint
        remaining = cp.remaining_files
        total = len(cp.input_files)
        
        if interactive:
            self._print_header("📁 FILE PROCESSOR - Processing")
            print(f"\n🚀 Starting processing of {len(remaining)} files")
            print(f"   Provider: {cp.provider}")
            print(f"   Model:    {cp.model}")
            from src import web_server
            current_thinking = web_server.CONFIG.get("thinking_enabled", False)
            thinking_status = "ON" if current_thinking else "OFF"
            print(f"   Thinking: {thinking_status} (System Setting)")
            print(f"   Delay:    {cp.delay_between_requests}s")
            print("\n[P] Pause  [S] Stop (saves progress)  [Esc] Abort")
            print("─" * 60)
        
        self.status = ToolStatus.RUNNING
        result = ToolResult(success=True, total_count=total)
        
        # Import API client
        from src.api_client import call_api_with_retry
        from src import web_server
        
        for i, file_path in enumerate(remaining):
            # Check for abort/pause
            if self.check_abort():
                self.status = ToolStatus.CANCELLED
                self.checkpoint_manager.save(cp)
                result.message = "Aborted by user"
                result.success = False
                break
            
            if not self.check_pause():
                # Paused - save and wait
                self.checkpoint_manager.save(cp)
                if interactive:
                    print("\n⏸️  Paused. Press Enter to resume, 'q' to quit...")
                    try:
                        resume = input().strip().lower()
                        if resume == 'q':
                            result.message = "Stopped by user"
                            break
                        self.request_resume()
                    except (EOFError, KeyboardInterrupt):
                        result.message = "Stopped by user"
                        break
            
            # Process file
            file_path_obj = Path(file_path)
            progress = f"[{len(cp.completed_files) + len(cp.failed_files) + 1}/{total}]"
            
            if interactive:
                print(f"\n{progress} Processing: {file_path_obj.name}")
            
            try:
                # Check for large files
                file_size = file_path_obj.stat().st_size
                is_large = file_size > MAX_INLINE_SIZE
                is_audio = is_audio_file(file_path_obj)
                
                response = None
                
                if is_large:
                    if interactive:
                        print(f"   ⚠️ Large file: {file_size / (1024*1024):.1f} MB")
                    
                    # Get handling mode (prompt if needed)
                    mode = self._get_large_file_mode(file_path_obj, is_audio, interactive)
                    
                    if mode == LARGE_FILE_MODE_SKIP:
                        cp.mark_failed(file_path, "Skipped large file")
                        if interactive:
                            print(f"   ⏭️ Skipped")
                        continue
                    
                    elif mode == LARGE_FILE_MODE_CHUNKING and is_audio:
                        # Use FFmpeg chunking
                        response = self._process_audio_with_chunking(
                            file_path_obj, cp.prompt_text, cp, interactive
                        )
                    
                    else:
                        # Use Files API
                        response = self._process_with_files_api(
                            file_path_obj, cp.prompt_text, cp, interactive
                        )
                else:
                    # Standard inline processing
                    response = self._process_file_inline(
                        file_path_obj, cp.prompt_text, cp, interactive
                    )
                
                if response is None:
                    raise Exception("No response from processing")
                
                # Handle output
                if cp.output_mode == "individual":
                    output_path = self.file_handler.get_output_path(
                        file_path_obj,
                        Path(cp.output_path),
                        cp.naming_template,
                        cp.output_extension,
                        index=len(cp.completed_files)
                    )
                    
                    # Write output
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(response)
                    
                    result.output_paths.append(str(output_path))
                    if interactive:
                        print(f"   ✅ → {output_path.name}")
                else:
                    # Combined mode
                    cp.append_combined_content(file_path, response)
                    if interactive:
                        print(f"   ✅ Added to combined output")
                
                cp.mark_completed(file_path)
                result.processed_count += 1
                
            except Exception as e:
                error_msg = str(e)[:100]
                cp.mark_failed(file_path, error_msg)
                result.add_error(file_path, error_msg)
                if interactive:
                    print(f"   ❌ Error: {error_msg}")
            
            # Save checkpoint after each file
            self.checkpoint_manager.save(cp)
            
            # Delay between requests (except for last file)
            if i < len(remaining) - 1 and cp.delay_between_requests > 0:
                time.sleep(cp.delay_between_requests)
        
        # Handle combined output
        if cp.output_mode == "combined" and cp.combined_output_content:
            combined_path = self.file_handler.get_output_path(
                Path(cp.input_path),
                Path(cp.output_path),
                f"batch_output_{{date}}_{{time}}",
                cp.output_extension,
                index=0
            )
            combined_path.parent.mkdir(parents=True, exist_ok=True)
            with open(combined_path, "w", encoding="utf-8") as f:
                f.write(cp.combined_output_content)
            result.output_path = str(combined_path)
            if interactive:
                print(f"\n📄 Combined output: {combined_path}")
        
        # Final summary
        if interactive:
            print("\n" + "─" * 60)
            print(f"✅ Completed: {result.processed_count}/{total}")
            if result.failed_count > 0:
                print(f"❌ Failed: {result.failed_count}")
            print("─" * 60)
        
        # Clear checkpoint if fully complete
        if cp.is_complete:
            self.checkpoint_manager.clear()
            result.message = f"Processed {result.processed_count} files successfully"
        else:
            result.message = f"Processed {result.processed_count}/{total} files"
        
        self.status = ToolStatus.COMPLETED
        return result
    
    # ─────────────────────────────────────────────────────────────────
    # Resume from checkpoint
    # ─────────────────────────────────────────────────────────────────
    
    def _prompt_resume_checkpoint(self) -> Optional[bool]:
        """
        Prompt user to resume from checkpoint.
        
        Returns:
            True to resume, False to start new, None to cancel
        """
        checkpoint = self.checkpoint_manager.load()
        if not checkpoint:
            return False
        
        summary = checkpoint.get_summary()
        
        self._print_header("⏸️  CHECKPOINT FOUND")
        print(f"\nPrevious session: {summary['created_at'][:19]}")
        print(f"Progress: {summary['completed']}/{summary['total_files']} files completed")
        print(f"Prompt: {summary['prompt_key']}")
        print(f"Output: {summary['output_path']}")
        
        print("\n[R] Resume from checkpoint")
        print("[N] Start new session (clears checkpoint)")
        print("[Q] Cancel")
        
        try:
            choice = input("\nChoice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        
        if choice == 'r':
            return True
        elif choice == 'n':
            return False
        else:
            return None
    
    def _resume_from_checkpoint(self) -> ToolResult:
        """Resume processing from saved checkpoint"""
        self._current_checkpoint = self.checkpoint_manager.load()
        if not self._current_checkpoint:
            return ToolResult(success=False, message="Failed to load checkpoint")
        
        return self._execute_processing()
    
    # ─────────────────────────────────────────────────────────────────
    # Large File Handling
    # ─────────────────────────────────────────────────────────────────
    
    def _get_large_file_mode(self, filepath: Path, is_audio: bool, interactive: bool) -> str:
        """
        Determine how to handle a large file.
        
        Args:
            filepath: Path to the file
            is_audio: Whether file is audio
            interactive: Whether to prompt user
            
        Returns:
            Mode string: LARGE_FILE_MODE_FILES_API, LARGE_FILE_MODE_CHUNKING, or LARGE_FILE_MODE_SKIP
        """
        # Check if we already have a mode for this file
        cached = self._large_file_mode.get(str(filepath))
        if cached:
            return cached
        
        if not interactive:
            # Non-interactive: default to Files API
            return LARGE_FILE_MODE_FILES_API
        
        print(f"\n   Large file detected: {filepath.name}")
        print(f"   Options:")
        print(f"   [1] Upload via Files API (recommended)")
        
        if is_audio and self.audio_processor.is_available():
            print(f"   [2] Split into chunks with FFmpeg (local processing)")
            print(f"   [3] Skip this file")
        else:
            if is_audio and not self.audio_processor.is_available():
                print(f"   [2] Skip this file (FFmpeg not available for chunking)")
            else:
                print(f"   [2] Skip this file")
        
        try:
            choice = input("   Choice [1]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return LARGE_FILE_MODE_SKIP
        
        if choice == "2" and is_audio and self.audio_processor.is_available():
            mode = LARGE_FILE_MODE_CHUNKING
        elif choice == "2" or choice == "3":
            mode = LARGE_FILE_MODE_SKIP
        else:
            mode = LARGE_FILE_MODE_FILES_API
        
        # Ask about applying to all similar files
        try:
            apply_all = input("   Apply to all large files? [y/N]: ").strip().lower()
            if apply_all == 'y':
                # Cache for all large files
                self._large_file_mode["_default"] = mode
        except (EOFError, KeyboardInterrupt):
            pass
        
        self._large_file_mode[str(filepath)] = mode
        return mode
    
    def _process_file_inline(
        self,
        filepath: Path,
        prompt: str,
        checkpoint: FileProcessorCheckpoint,
        interactive: bool
    ) -> Optional[str]:
        """
        Process a file using inline base64 data.
        
        Args:
            filepath: Path to file
            prompt: Processing prompt
            checkpoint: Current checkpoint
            interactive: Show progress
            
        Returns:
            Response text or None on failure
        """
        from src.api_client import call_api_with_retry
        from src import web_server
        
        # Build message
        message = self.file_handler.build_api_message(filepath, prompt, include_filename=True)
        
        # Call API
        response, error = call_api_with_retry(
            provider=checkpoint.provider,
            messages=[message],
            model_override=checkpoint.model if checkpoint.model else None,
            config=web_server.CONFIG,
            ai_params=web_server.AI_PARAMS,
            key_managers=web_server.KEY_MANAGERS
        )
        
        if error:
            raise Exception(error)
        
        return response
    
    def _process_with_files_api(
        self,
        filepath: Path,
        prompt: str,
        checkpoint: FileProcessorCheckpoint,
        interactive: bool
    ) -> Optional[str]:
        """
        Process a file using the Gemini Files API.
        
        Args:
            filepath: Path to file
            prompt: Processing prompt
            checkpoint: Current checkpoint
            interactive: Show progress
            
        Returns:
            Response text or None on failure
        """
        from src.api_client import call_api_with_retry
        from src import web_server
        from src.providers.gemini_native import GeminiNativeProvider
        
        # Get the provider
        provider_name = checkpoint.provider.lower()
        if provider_name != "google":
            raise Exception("Files API only supported for Google/Gemini provider")
        
        key_manager = web_server.KEY_MANAGERS.get(provider_name)
        if not key_manager:
            raise Exception("Google key manager not found")
        
        # Create provider instance for upload
        provider = GeminiNativeProvider(key_manager=key_manager, config=web_server.CONFIG)
        
        # Upload file
        if interactive:
            print(f"   📤 Uploading to Files API...")
        
        uploaded, error = provider.upload_file(filepath)
        if error:
            raise Exception(f"Upload failed: {error}")
        
        if interactive:
            print(f"   ✅ Uploaded: {uploaded.name}")
        
        try:
            # Build message with file reference
            file_type = self.file_handler.detect_type(filepath)
            
            message = {
                "role": "user",
                "content": [
                    {
                        "type": "file_data",
                        "file_data": {
                            "mime_type": uploaded.mime_type,
                            "file_uri": uploaded.uri
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }
            
            # Call API
            response, error = call_api_with_retry(
                provider=checkpoint.provider,
                messages=[message],
                model_override=checkpoint.model if checkpoint.model else None,
                config=web_server.CONFIG,
                ai_params=web_server.AI_PARAMS,
                key_managers=web_server.KEY_MANAGERS
            )
            
            if error:
                raise Exception(error)
            
            return response
            
        finally:
            # Clean up uploaded file (optional - they auto-delete after 48h)
            if interactive:
                print(f"   🗑️ Cleaning up uploaded file...")
            provider.delete_file(uploaded.name)
    
    def _preprocess_audio_if_needed(
        self,
        filepath: Path,
        interactive: bool
    ) -> Tuple[Path, Optional['ProcessingResult']]:
        """
        Apply audio preprocessing if configured.
        
        Args:
            filepath: Original audio file path
            interactive: Show progress
            
        Returns:
            Tuple of (path to use, ProcessingResult if temp file created)
        """
        from .audio_processor import ProcessingResult
        
        if not self._audio_preprocessing:
            return filepath, None
        
        preprocess_type = self._audio_preprocessing.get("type")
        
        # Get optimization settings if present
        optimization = None
        opt_config = self._audio_preprocessing.get("optimization")
        if opt_config:
            optimization = OutputOptimization(
                convert_to_mono=opt_config.get("convert_to_mono", False),
                sample_rate=opt_config.get("sample_rate"),
                bitrate_kbps=opt_config.get("bitrate_kbps")
            )
            if interactive and optimization.describe() != "No optimization":
                print(f"   📦 Output optimization: {optimization.describe()}")
        
        # If we only have optimization (no effects), apply it alone
        if not preprocess_type and optimization:
            if interactive:
                print(f"   📦 Applying file size optimization...")
            
            result = self.audio_processor.apply_optimization_only(filepath, optimization)
            
            if result.success:
                if interactive:
                    print(f"   ✅ File optimized")
                return result.output_path, result
            else:
                if interactive:
                    print(f"   ⚠️ Optimization failed: {result.error}")
                return filepath, None
        
        if preprocess_type == "amplify":
            volume_percent = self._audio_preprocessing.get("volume_percent", 100)
            if volume_percent == 100 and not optimization:
                return filepath, None
            
            if interactive:
                boost = volume_percent - 100
                print(f"   🔊 Amplifying volume by {boost:+d}%...")
            
            result = self.audio_processor.amplify_volume(
                filepath,
                volume_percent=volume_percent
            )
            
            if result.success:
                if interactive:
                    print(f"   ✅ Volume adjusted")
                # If we have optimization, apply it to the amplified result
                if optimization:
                    opt_result = self.audio_processor.apply_optimization_only(
                        result.output_path, optimization
                    )
                    result.cleanup()
                    if opt_result.success:
                        return opt_result.output_path, opt_result
                    # Fall through with original result on optimization failure
                return result.output_path, result
            else:
                if interactive:
                    print(f"   ⚠️ Volume adjustment failed: {result.error}")
                return filepath, None
        
        elif preprocess_type == "normalize":
            if interactive:
                print(f"   🔊 Normalizing audio...")
            
            result = self.audio_processor.amplify_volume(
                filepath,
                normalize=True
            )
            
            if result.success:
                if interactive:
                    print(f"   ✅ Audio normalized")
                # If we have optimization, apply it to the normalized result
                if optimization:
                    opt_result = self.audio_processor.apply_optimization_only(
                        result.output_path, optimization
                    )
                    result.cleanup()
                    if opt_result.success:
                        return opt_result.output_path, opt_result
                return result.output_path, result
            else:
                if interactive:
                    print(f"   ⚠️ Normalization failed: {result.error}")
                return filepath, None
        
        elif preprocess_type == "amplify_normalize":
            # Two-step: amplify first, then normalize
            volume_percent = self._audio_preprocessing.get("volume_percent", 100)
            
            if interactive:
                boost = volume_percent - 100
                print(f"   🔊 Amplifying volume by {boost:+d}% + normalizing...")
            
            # Step 1: Amplify
            amplify_result = self.audio_processor.amplify_volume(
                filepath,
                volume_percent=volume_percent
            )
            
            if not amplify_result.success:
                if interactive:
                    print(f"   ⚠️ Amplification failed: {amplify_result.error}")
                return filepath, None
            
            # Step 2: Normalize the amplified audio
            normalize_result = self.audio_processor.amplify_volume(
                amplify_result.output_path,
                normalize=True
            )
            
            # Clean up intermediate file
            amplify_result.cleanup()
            
            if normalize_result.success:
                if interactive:
                    print(f"   ✅ Audio amplified and normalized")
                # If we have optimization, apply it
                if optimization:
                    opt_result = self.audio_processor.apply_optimization_only(
                        normalize_result.output_path, optimization
                    )
                    normalize_result.cleanup()
                    if opt_result.success:
                        return opt_result.output_path, opt_result
                return normalize_result.output_path, normalize_result
            else:
                if interactive:
                    print(f"   ⚠️ Normalization failed: {normalize_result.error}")
                return filepath, None
        
        elif preprocess_type == "preset":
            # Apply a voice enhancement preset
            preset_id = self._audio_preprocessing.get("preset_id", "")
            intensity_str = self._audio_preprocessing.get("intensity", "medium")
            
            preset = get_preset(preset_id)
            if not preset:
                if interactive:
                    print(f"   ⚠️ Preset not found: {preset_id}")
                return filepath, None
            
            intensity = Intensity(intensity_str)
            
            if interactive:
                print(f"   🎤 Applying {preset.name} ({intensity_str})...")
            
            # Pass optimization directly to apply_preset
            result = self.audio_processor.apply_preset(
                filepath,
                preset_id,
                intensity=intensity,
                optimization=optimization
            )
            
            if result.success:
                if interactive:
                    print(f"   ✅ Voice enhancement applied")
                return result.output_path, result
            else:
                if interactive:
                    print(f"   ⚠️ Enhancement failed: {result.error}")
                return filepath, None
        
        elif preprocess_type == "custom":
            # Apply custom effect chain
            effects_config = self._audio_preprocessing.get("effects", [])
            
            if not effects_config:
                # Still apply optimization if present
                if optimization:
                    result = self.audio_processor.apply_optimization_only(filepath, optimization)
                    if result.success:
                        return result.output_path, result
                return filepath, None
            
            effects = [AudioEffect(e["name"], e.get("params", {})) for e in effects_config]
            
            if interactive:
                effect_names = ", ".join(e.name for e in effects)
                print(f"   🔧 Applying custom effects: {effect_names}...")
            
            # Pass optimization directly to apply_effects
            result = self.audio_processor.apply_effects(
                filepath,
                effects,
                optimization=optimization
            )
            
            if result.success:
                if interactive:
                    print(f"   ✅ Custom effects applied")
                return result.output_path, result
            else:
                if interactive:
                    print(f"   ⚠️ Effects failed: {result.error}")
                return filepath, None
        
        return filepath, None
    
    def _process_audio_with_chunking(
        self,
        filepath: Path,
        prompt: str,
        checkpoint: FileProcessorCheckpoint,
        interactive: bool
    ) -> Optional[str]:
        """
        Process audio file by splitting into chunks.
        
        Args:
            filepath: Path to audio file
            prompt: Processing prompt
            checkpoint: Current checkpoint
            interactive: Show progress
            
        Returns:
            Merged transcript or None on failure
        """
        from src.api_client import call_api_with_retry
        from src import web_server
        
        # Apply preprocessing if configured
        process_path, preprocess_result = self._preprocess_audio_if_needed(filepath, interactive)
        
        if interactive:
            print(f"   ✂️ Splitting audio with FFmpeg...")
        
        # Split the audio (use preprocessed path)
        result = self.audio_processor.split_audio(process_path)
        
        if not result.success:
            # Clean up preprocessing temp file before raising
            if preprocess_result:
                preprocess_result.cleanup()
            raise Exception(f"Chunking failed: {result.error}")
        
        if interactive:
            print(f"   📊 Created {len(result.chunks)} chunks")
        
        try:
            chunk_outputs = []
            
            for i, chunk in enumerate(result.chunks):
                if interactive:
                    print(f"   [{i+1}/{len(result.chunks)}] Processing {chunk.time_range_str}...")
                
                # Build message for chunk
                message = self.file_handler.build_api_message(chunk.path, prompt, include_filename=False)
                
                # Call API
                response, error = call_api_with_retry(
                    provider=checkpoint.provider,
                    messages=[message],
                    model_override=checkpoint.model if checkpoint.model else None,
                    config=web_server.CONFIG,
                    ai_params=web_server.AI_PARAMS,
                    key_managers=web_server.KEY_MANAGERS
                )
                
                if error:
                    if interactive:
                        print(f"      ⚠️ Chunk error: {error[:50]}")
                    continue
                
                if response:
                    chunk_outputs.append((chunk, response))
                    if interactive:
                        print(f"      ✅ Done")
                
                # Delay between chunks
                if i < len(result.chunks) - 1 and checkpoint.delay_between_requests > 0:
                    time.sleep(checkpoint.delay_between_requests)
            
            if not chunk_outputs:
                raise Exception("All chunks failed to process")
            
            # Merge outputs
            if interactive:
                print(f"   📝 Merging {len(chunk_outputs)} transcripts...")
            
            merged = self.audio_processor.merge_transcripts(chunk_outputs, include_timestamps=True)
            return merged
            
        finally:
            # Clean up temp files
            result.cleanup()
            # Clean up preprocessing temp file
            if preprocess_result:
                preprocess_result.cleanup()
            if interactive:
                print(f"   🗑️ Cleaned up temporary files")
    
    # ─────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────
    
    def _print_header(self, title: str):
        """Print a section header"""
        print(f"\n{'═' * 60}")
        print(f" {title}")
        print(f"{'═' * 60}")


def show_tools_menu(endpoints: Dict[str, str] = None) -> bool:
    """
    Display the Tools menu and handle selection.
    
    Args:
        endpoints: Endpoint prompts from config.ini
    
    Returns:
        True if a tool was run, False if cancelled
    """
    if HAVE_RICH:
        print_panel(
            "[1] 📁 File Processor   Process files with AI prompts\n"
            "[2] 🔜 Coming Soon...   More tools planned\n\n"
            "[B] ← Back to main menu",
            title="🧰 TOOLS",
            border_style="cyan"
        )
    else:
        print(f"\n{'═' * 60}")
        print(" 🧰 TOOLS")
        print(f"{'═' * 60}")
        print()
        print("  [1] 📁 File Processor   Process files with AI prompts")
        print("  [2] 🔜 Coming Soon...   More tools planned")
        print()
        print("  [B] ← Back to main menu")
        print(f"{'═' * 60}")
    
    try:
        choice = input("\nSelect tool: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    
    if choice == '1':
        # Import web_server config
        from src import web_server
        
        processor = FileProcessor(
            config=web_server.CONFIG,
            endpoints=endpoints
        )
        result = processor.run_interactive()
        
        if result.success:
            print_success(f"\n{result.message}")
        else:
            if result.message != "Cancelled":
                print_warning(f"\n{result.message}")
        
        return True
    
    elif choice == 'b' or choice == '':
        return False
    
    else:
        print_warning("Coming soon!")
        return False