"""Process uploaded audio files using the same pipeline as live recording."""

import sys
import logging
import threading
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.meeting_manager import MeetingManager, MeetingState
from src.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def process_audio_file(audio_file_path: str):
    """
    Process an uploaded audio file through the full production pipeline:
      split into 30s chunks → transcribe_chunk() → analyze_chunk()
      → Haiku ASR cleanup → Sonnet summary → HTML with footnotes

    Args:
        audio_file_path: Path to the audio file (WAV, M4A, MP3, etc.)
    """
    import tkinter as tk

    audio_file = Path(audio_file_path)
    if not audio_file.exists():
        print(f"Error: File not found: {audio_file}")
        return

    print(f"\n{'='*60}")
    print(f"Processing: {audio_file.name}")
    print(f"File size:  {audio_file.stat().st_size / (1024*1024):.1f} MB")
    print(f"{'='*60}\n")
    print("Pipeline: split → transcribe → analyze → Haiku cleanup → Sonnet summary")
    print("(same as live recording — this may take several minutes)\n")

    # --- Status window ---
    status_window = None
    status_label = None
    progress_label = None

    def create_status_window():
        nonlocal status_window, status_label, progress_label
        status_window = tk.Tk()
        status_window.title("Pilot — Processing Upload")
        status_window.geometry("440x140")
        status_window.attributes('-topmost', True)
        status_window.resizable(False, False)

        tk.Label(
            status_window,
            text=f"Processing: {audio_file.name}",
            font=("Arial", 10, "bold")
        ).pack(pady=(12, 2))

        status_label = tk.Label(status_window, text="Starting...", font=("Arial", 9))
        status_label.pack(pady=2)

        progress_label = tk.Label(status_window, text="", font=("Arial", 9), fg="#555")
        progress_label.pack(pady=2)

        tk.Label(
            status_window,
            text="Do not close this window",
            font=("Arial", 8), fg="gray"
        ).pack(pady=(4, 0))

        status_window.protocol("WM_DELETE_WINDOW", lambda: None)
        status_window.mainloop()

    window_thread = threading.Thread(target=create_status_window, daemon=True)
    window_thread.start()
    time.sleep(0.5)  # Let window appear

    def update_status(step: str, done: int = 0, total: int = 0):
        """Thread-safe status update."""
        if status_label and status_window:
            try:
                status_label.config(text=step)
                if total:
                    progress_label.config(text=f"Chunk {done} of {total}")
                else:
                    progress_label.config(text="")
                status_window.update()
            except Exception:
                pass
        if total:
            print(f"  [{done}/{total}] {step}")
        else:
            print(f"  {step}")

    # --- Processing ---
    manager = MeetingManager()

    try:
        from src.minimal_notifier import MinimalNotifier
        notifier = MinimalNotifier()
        notifier.notify(f"Processing {audio_file.name}...", duration=5)
    except Exception:
        notifier = None

    try:
        html_path = manager.process_uploaded_file(
            audio_path=audio_file,
            status_callback=update_status
        )

        if html_path:
            print(f"\n{'='*60}")
            print("Processing complete!")
            print(f"Summary: {html_path}")
            print(f"{'='*60}\n")

            update_status("Complete! Opening in browser...")

            if notifier:
                notifier.notify("Meeting summary ready!", duration=3)

            import os
            if sys.platform == 'win32':
                os.startfile(str(html_path))
        else:
            print("\nError: Processing failed — check logs for details")
            update_status("ERROR — check logs")
            if notifier:
                notifier.notify("Processing failed — see console", duration=5)

    except Exception as e:
        logger.error(f"Error processing audio file: {e}", exc_info=True)
        print(f"\nError: {e}")
        update_status(f"ERROR: {str(e)[:60]}")

    finally:
        time.sleep(5)
        if status_window:
            try:
                status_window.destroy()
            except Exception:
                pass


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("\nUsage: python process_audio_file.py <path_to_audio_file>")
        print("\nSupported formats: WAV, M4A (iPhone voice memos), MP3, etc.")
        print("\nExample:")
        print("  python process_audio_file.py \"C:\\Users\\YourName\\Downloads\\meeting.m4a\"")
        print()
        sys.exit(1)

    process_audio_file(sys.argv[1])
