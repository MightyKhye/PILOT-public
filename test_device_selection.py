"""Test script to verify device selection with config.ini"""
import sys
sys.path.insert(0, '.')

from src.config import Config
from src.audio_capture import AudioCapture
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

print("="*60)
print("DEVICE SELECTION TEST")
print("="*60)

# Load config
Config.load_user_config()
print(f"Config.MICROPHONE_DEVICE_INDEX = {Config.MICROPHONE_DEVICE_INDEX}")
print()

# Create AudioCapture instance
capture = AudioCapture()

# Test device selection (same as app does)
print("Calling get_default_microphone with device_index from config...")
device = capture.get_default_microphone(device_index=Config.MICROPHONE_DEVICE_INDEX)

if device:
    print(f"\n✓ Selected device:")
    print(f"  Index: {device['index']}")
    print(f"  Name: {device['name']}")
    print(f"  Sample Rate: {device['defaultSampleRate']} Hz")
    print(f"  Input Channels: {device['maxInputChannels']}")
else:
    print("\n✗ No device selected!")

capture.cleanup()
print("\n" + "="*60)
