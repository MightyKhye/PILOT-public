"""Simple CLI to control Meeting Listener without system tray."""
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.meeting_manager import MeetingManager, MeetingState
from src.config import Config

def main():
    print("=" * 70)
    print("MEETING LISTENER - Command Line Controller")
    print("=" * 70)

    manager = MeetingManager()

    while True:
        print("\nOptions:")
        print("  1. Start Recording")
        print("  2. Stop Recording")
        print("  3. View Status")
        print("  4. Exit")

        choice = input("\nEnter choice (1-4): ").strip()

        if choice == "1":
            print("\n[Starting recording...]")
            print("Play audio or speak into your microphone.")
            print("The system will capture audio and transcribe every 30 seconds.\n")

            success = manager.start_meeting()
            if success:
                print("[OK] Recording started!")
                print("- Audio is being captured from your speakers")
                print("- Transcriptions will be sent to AssemblyAI")
                print("- Claude will analyze for action items")
                print("- You'll get Windows notifications")
            else:
                print("[ERROR] Failed to start recording")

        elif choice == "2":
            print("\n[Stopping recording...]")
            summary_path = manager.stop_meeting()

            if summary_path:
                print(f"[OK] Recording stopped!")
                print(f"Summary saved to: {summary_path}")
                print(f"\nMeeting info:")
                info = manager.get_meeting_info()
                print(f"  Duration: {info['duration']}")
                print(f"  Chunks: {info['chunks_processed']}")
                print(f"  Analyses: {info['analyses']}")
            else:
                print("[ERROR] No recording in progress")

        elif choice == "3":
            info = manager.get_meeting_info()
            print(f"\nStatus: {info['state']}")

            if info['state'] != 'idle':
                print(f"Meeting ID: {info['meeting_id']}")
                print(f"Duration: {info['duration']}")
                print(f"Chunks processed: {info['chunks_processed']}")
                print(f"Analyses: {info['analyses']}")
            else:
                print("No meeting in progress")

        elif choice == "4":
            print("\nExiting...")
            if manager.get_state() != MeetingState.IDLE:
                print("Stopping current recording first...")
                manager.stop_meeting()
            manager.cleanup()
            break
        else:
            print("[ERROR] Invalid choice")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
