"""Test the recording indicator directly."""

import time
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.recording_indicator import RecordingIndicator
from src.meeting_manager import MeetingState

print("Testing Recording Indicator...")
print("=" * 50)

indicator = RecordingIndicator()
indicator.start()

print("Waiting for indicator to initialize...")
time.sleep(2)

print("\n1. Setting state to RECORDING (should show blinking tab)")
indicator.update_state(MeetingState.RECORDING, chunk_count=0)
print("   -> Tab should appear on right edge with blinking red circle")
print("   -> Hover over it to see it expand")

time.sleep(10)

print("\n2. Updating chunk count")
indicator.update_state(MeetingState.RECORDING, chunk_count=5)

time.sleep(5)

print("\n3. Setting state to PROCESSING (orange)")
indicator.update_state(MeetingState.PROCESSING, chunk_count=5)

time.sleep(3)

print("\n4. Back to RECORDING")
indicator.update_state(MeetingState.RECORDING, chunk_count=6)

time.sleep(5)

print("\n5. Setting state to IDLE (should hide)")
indicator.update_state(MeetingState.IDLE, chunk_count=0)

time.sleep(2)

print("\nTest complete! Stopping indicator...")
indicator.stop()
time.sleep(1)

print("Done!")
