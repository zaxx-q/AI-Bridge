#!/usr/bin/env python3
"""Test runner that saves results to a file"""
import sys
import unittest
import io

# Add parent directory to path
sys.path.insert(0, '..')

# Import test module
from test_streaming_retry import TestStreamingRetry

if __name__ == '__main__':
    # Create output buffer
    output = io.StringIO()
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestStreamingRetry)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2, stream=output)
    result = runner.run(suite)
    
    # Get output
    test_output = output.getvalue()
    
    # Add summary
    summary = f"\n{'='*70}\n"
    summary += f"Tests run: {result.testsRun}\n"
    summary += f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}\n"
    summary += f"Failures: {len(result.failures)}\n"
    summary += f"Errors: {len(result.errors)}\n"
    summary += f"{'='*70}\n"
    
    full_output = test_output + summary
    
    # Write to file
    with open('test_results.txt', 'w') as f:
        f.write(full_output)
    
    # Also print to console
    print(full_output)
    
    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)