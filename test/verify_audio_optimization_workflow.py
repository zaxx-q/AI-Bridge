#!/usr/bin/env python3
"""
Verify Audio Optimization Workflow Integration.
Simulates the interactive workflow steps to ensure configuration is built correctly.
"""
import sys
import unittest
import io
from unittest.mock import MagicMock, patch
from pathlib import Path
from typing import Dict, Any

# Force UTF-8 for test output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.tools.file_processor import FileProcessor, ScanResult
from src.tools.file_handler import FileInfo
from src.tools.audio_processor import OutputOptimization

class TestAudioOptimizationWorkflow(unittest.TestCase):
    def setUp(self):
        self.processor = FileProcessor()
        # Mock dependencies
        self.processor.audio_processor.is_available = MagicMock(return_value=True)
        self.processor.audio_processor.is_ffplay_available = MagicMock(return_value=False)
        self.processor.audio_processor.get_audio_info = MagicMock(return_value=MagicMock(
            channels=2, 
            sample_rate=44100, 
            duration_seconds=60,
            size_bytes=1000000
        ))
        
        # Mock file info
        self.mock_file = FileInfo(
            path=Path("test/test_audio.mp3"),
            file_type="audio",
            extension=".mp3",
            size=1000000
        )
        self.scan_result = ScanResult(
            input_path=Path("test"),
            files=[self.mock_file],
            by_type={"audio": [self.mock_file]},
            warnings=[]
        )

    @patch('builtins.input')
    def test_workflow_no_effects_with_quick_optimization(self, mock_input):
        """Test: Skip effects (1), apply Quick Optimization (1)"""
        # Sequence:
        # 1. Effects menu -> "1" (No effects)
        # 2. Optimization menu -> "1" (Quick presets)
        # 3. Presets menu -> "1" (Voice small)
        # 4. Optimization menu -> "C" (Continue)
        mock_input.side_effect = ["1", "1", "1", "c"]
        
        # Part 1: Effects
        effects_config = self.processor._step_audio_preprocessing(self.scan_result)
        self.assertEqual(effects_config, {}, "Should return empty config for no effects")
        
        # Part 2: Optimization (passing in empty effects config)
        final_config = self.processor._step_audio_optimization(self.scan_result, effects_config)
        
        # Verify optimization was added
        self.assertIn("optimization", final_config)
        opt = final_config["optimization"]
        self.assertTrue(opt["convert_to_mono"])
        self.assertEqual(opt["sample_rate"], 16000)
        self.assertEqual(opt["bitrate_kbps"], 32)

    @patch('builtins.input')
    def test_workflow_effects_plus_custom_optimization(self, mock_input):
        """Test: Apply detailed effects, then Custom Optimization"""
        # Sequence:
        # 1. Effects menu -> "2" (Normalize)
        # 2. Effects menu -> "C" (Continue)
        # 3. Optimization menu -> "2" (Custom settings)
        # 4. Custom settings -> "2" (Mono)
        # 5. Custom settings -> "1" (Sample rate option 1)
        # 6. Custom settings -> "1" (Bitrate option 1)
        # 7. Optimization menu -> "C" (Continue)
        
        # Note: _step_file_optimization inputs depend on SAMPLE_RATE_OPTIONS ordering
        # Using "K" (Keep) for rates/bitrates to handle varying dict keys simpler
        mock_input.side_effect = [
            # Effects
            "2", # Normalize
            "c", # Continue
            
            # Optimization
            "2", # Custom settings
                 "2", # Mono
                 "k", # Keep sample rate
                 "k", # Keep bitrate
            "c"  # Continue
        ]
        
        # Part 1: Effects
        effects_config = self.processor._step_audio_preprocessing(self.scan_result)
        self.assertEqual(effects_config["type"], "normalize")
        
        # Part 2: Optimization
        final_config = self.processor._step_audio_optimization(self.scan_result, effects_config)
        
        # Verify both exist
        self.assertEqual(final_config["type"], "normalize")
        self.assertIn("optimization", final_config)
        self.assertTrue(final_config["optimization"]["convert_to_mono"])

    @patch('builtins.input')
    def test_workflow_skip_all(self, mock_input):
        """Test: Skip Effects and Skip Optimization"""
        # Sequence:
        # 1. Effects -> "1" (Skip)
        # 2. Optimization -> "3" (Skip)
        # 3. Optimization -> "C" (Continue)
        mock_input.side_effect = ["1", "3", "c"]
        
        effects_config = self.processor._step_audio_preprocessing(self.scan_result)
        final_config = self.processor._step_audio_optimization(self.scan_result, effects_config)
        
        self.assertEqual(final_config, {})
        self.assertNotIn("optimization", final_config)

if __name__ == '__main__':
    unittest.main()