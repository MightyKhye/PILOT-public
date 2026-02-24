"""
Quick test script to verify audio recording fix.
Run this AFTER restarting Pilot with fresh code.
"""

import sys
sys.path.insert(0, '.')

import wave
import time
from pathlib import Path
from src.config import Config
from src.audio_capture import AudioCapture

print("="*70)
print("PILOT AUDIO FIX VERIFICATION TEST")
print("="*70)
print()

# Load config
Config.load_user_config()
print(f"[1] Config loaded")
print(f"    Microphone device index: {Config.MICROPHONE_DEVICE_INDEX}")
print()

# Create audio capture
capture = AudioCapture(chunk_duration=5)  # 5 seconds for quick test
print(f"[2] Audio capture created")
print()

# Test device selection
device = capture.get_default_microphone(device_index=Config.MICROPHONE_DEVICE_INDEX)
if device:
    print(f"[3] Device selection test:")
    print(f"    Index: {device['index']}")
    print(f"    Name: {device['name']}")
    print(f"    Sample Rate: {device['defaultSampleRate']} Hz")
    print(f"    Channels: {device['maxInputChannels']}")

    if device['defaultSampleRate'] == 48000.0:
        print(f"    [OK] Correct sample rate!")
    else:
        print(f"    [WARNING] Expected 48000 Hz, got {device['defaultSampleRate']} Hz")
else:
    print("[3] [ERROR] No device selected!")
    capture.cleanup()
    sys.exit(1)

print()
print("[4] Starting 10-second test recording...")
print("    (Please make some sound - speak, play music, etc.)")
print()

try:
    # Start recording
    capture.start_recording(use_microphone=True, microphone_device_index=Config.MICROPHONE_DEVICE_INDEX)

    # Record for 10 seconds
    time.sleep(10)

    # Stop recording
    capture.stop_recording()

    print()
    print("[5] Recording stopped. Checking chunks...")
    print()

    # Get chunks
    chunks = []
    while True:
        chunk = capture.get_next_chunk(timeout=0.1)
        if not chunk:
            break
        chunks.append(chunk)

    if chunks:
        print(f"[6] Captured {len(chunks)} chunk(s)")
        print()

        for i, chunk in enumerate(chunks, 1):
            filename = chunk['filename']

            # Check WAV file properties
            with wave.open(str(filename), 'rb') as w:
                rate = w.getframerate()
                channels = w.getnchannels()
                duration = w.getnframes() / rate

            print(f"    Chunk {i}: {filename.name}")
            print(f"      Sample Rate: {rate} Hz", end="")
            if rate == 48000:
                print(" [OK]")
            else:
                print(f" [WARNING] Expected 48000 Hz")

            print(f"      Channels: {channels}", end="")
            if channels == 1:
                print(" [OK]")
            else:
                print(f" [WARNING] Expected 1 channel")

            print(f"      Duration: {duration:.1f}s")
            print()

        # Final verdict
        print("="*70)
        print("TEST RESULTS:")
        print("="*70)

        all_ok = all(
            chunk.get('sample_rate') == 48000 and chunk.get('channels') == 1
            for chunk in chunks
        )

        if all_ok and device['defaultSampleRate'] == 48000.0:
            print("[SUCCESS] Audio recording is working correctly!")
            print()
            print("Expected output:")
            print("  Device: Microphone Array (AMD Audio Device)")
            print("  Sample Rate: 48000 Hz")
            print("  Channels: 1 (mono)")
            print()
            print("Now test playback of the chunk file to verify audio quality.")
            print(f"Test file: {chunks[0]['filename']}")
        else:
            print("[WARNING] Some parameters don't match expected values.")
            print("Check the output above for details.")
    else:
        print("[WARNING] No chunks were captured. Recording may have failed.")

except KeyboardInterrupt:
    print()
    print("[INFO] Test interrupted by user")
except Exception as e:
    print()
    print(f"[ERROR] Test failed: {e}")
    import traceback
    traceback.print_exc()
finally:
    capture.cleanup()
    print()
    print("="*70)
    print("Test complete. Check logs/pilot.log for detailed logging.")
    print("="*70)
