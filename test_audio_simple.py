"""Simple audio test without Unicode."""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import with absolute path handling
from src.audio_capture import AudioCapture
import time

print("=" * 60)
print("AUDIO CAPTURE TEST")
print("=" * 60)

capture = AudioCapture(chunk_duration=5)

# Test 1: Find device
print("\n1. Checking for loopback device...")
device = capture.get_loopback_device()

if device:
    print("   [OK] Found:", device['name'])
    print("   Sample rate:", device['defaultSampleRate'], "Hz")
    print("   Channels:", device['maxInputChannels'])
else:
    print("   [FAIL] No loopback device found")
    sys.exit(1)

# Test 2: Record audio
print("\n2. Starting 10-second recording...")
print("   > Play some audio now (YouTube, music, etc.)")
print()

capture.start_recording()

if not capture.recording:
    print("   [FAIL] Could not start recording")
    sys.exit(1)

print("   [OK] Recording started")
print("   Recording", end="", flush=True)

for i in range(10):
    time.sleep(1)
    print(".", end="", flush=True)

print("\n\n3. Stopping recording...")
capture.stop_recording()

# Test 3: Check chunks
chunks = []
while True:
    chunk = capture.get_next_chunk(timeout=0.1)
    if not chunk:
        break
    chunks.append(chunk)

print(f"   [OK] Captured {len(chunks)} audio chunks\n")

if chunks:
    print("Chunks saved:")
    for i, chunk in enumerate(chunks, 1):
        print(f"  - {chunk['filename'].name} ({chunk['duration']:.1f}s)")

capture.cleanup()

print("\n" + "=" * 60)
print("TEST COMPLETE - Audio capture is working!")
print("=" * 60)
