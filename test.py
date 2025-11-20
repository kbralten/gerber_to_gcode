#!/usr/bin/env python3
"""
Simple test script to verify excellon_to_gcode.py is working correctly.
"""

import subprocess
import sys
import os

def run_test():
    """Run a basic test of the converter."""
    print("Testing excellon_to_gcode.py...")
    print("=" * 50)
    
    # Check if example.drl exists
    if not os.path.exists("example.drl"):
        print("❌ Error: example.drl not found")
        print("   Make sure you're running this from the project directory")
        return False
    
    # Run the converter
    try:
        result = subprocess.run(
            [sys.executable, "excellon_to_gcode.py", "example.drl", "-o", "test_output.nc"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print("❌ Error: Converter failed")
            print(result.stderr)
            return False
            
        print("✅ Converter ran successfully")
        print()
        print(result.stdout)
        
        # Check if output file was created
        if not os.path.exists("test_output.nc"):
            print("❌ Error: Output file not created")
            return False
            
        print("✅ Output file created: test_output.nc")
        
        # Check file size
        size = os.path.getsize("test_output.nc")
        if size < 100:
            print("❌ Error: Output file is too small")
            return False
            
        print(f"✅ Output file size: {size} bytes")
        
        # Read first few lines
        with open("test_output.nc", "r") as f:
            lines = [f.readline() for _ in range(5)]
        
        print()
        print("First few lines of output:")
        print("-" * 50)
        for line in lines:
            print(line.rstrip())
        print("-" * 50)
        
        # Clean up
        os.remove("test_output.nc")
        print()
        print("✅ Test file cleaned up")
        
        return True
        
    except subprocess.TimeoutExpired:
        print("❌ Error: Converter timed out")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("Excellon to G-code Test Suite")
    print("=" * 50)
    print()
    
    success = run_test()
    
    print()
    print("=" * 50)
    if success:
        print("✅ All tests passed!")
        print()
        print("You're ready to use excellon_to_gcode.py")
        print("Try: python excellon_to_gcode.py --help")
        sys.exit(0)
    else:
        print("❌ Tests failed")
        print()
        print("Please check the error messages above")
        sys.exit(1)
