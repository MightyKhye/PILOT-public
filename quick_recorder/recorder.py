"""Quick audio recorder with keyboard shortcut and overlay indicator."""

import sounddevice as sd
import soundfile as sf
import numpy as np
import tkinter as tk
from datetime import datetime
import threading
import logging
from pathlib import Path
import pytz
from pynput import keyboard

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RecordingIndicator:
    """Blinking red indicator overlay."""

    def __init__(self, on_click_callback):
        """Initialize indicator."""
        self.window = None
        self.canvas = None
        self.is_recording = False
        self.blink_state = False
        self.on_click_callback = on_click_callback

    def show(self):
        """Show the indicator."""
        self.window = tk.Tk()
        self.window.title("Recording")
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.attributes('-alpha', 0.7)

        # Position at bottom-right
        size = 50
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = screen_width - size - 10
        y = screen_height - size - 50

        self.window.geometry(f"{size}x{size}+{x}+{y}")

        # Canvas for red circle
        self.canvas = tk.Canvas(
            self.window,
            width=size,
            height=size,
            bg='black',
            highlightthickness=0
        )
        self.canvas.pack()

        # Click handler
        self.canvas.bind('<Button-1>', lambda e: self.on_click_callback())

        self.is_recording = True
        self._blink_loop()
        self.window.mainloop()

    def _blink_loop(self):
        """Blink the red circle."""
        if not self.is_recording or not self.window:
            return

        self.canvas.delete("all")
        color = '#FF0000' if self.blink_state else '#880000'
        self.canvas.create_oval(5, 5, 45, 45, fill=color, outline='')

        self.blink_state = not self.blink_state
        self.window.after(500, self._blink_loop)

    def hide(self):
        """Hide and destroy indicator."""
        self.is_recording = False
        if self.window:
            self.window.quit()
            self.window.destroy()
            self.window = None


class QuickRecorder:
    """Main recorder with keyboard shortcut."""

    def __init__(self):
        """Initialize recorder."""
        self.is_recording = False
        self.audio_data = []
        self.sample_rate = 44100
        self.recording_start_time = None
        self.indicator = None
        self.indicator_thread = None

        # Output directory
        self.output_dir = Path.home() / "Documents" / "Sound Recordings"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Quick Recorder initialized. Recordings saved to: {self.output_dir}")

    def toggle_recording(self):
        """Toggle recording on/off."""
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        """Start recording."""
        if self.is_recording:
            return

        logger.info("Starting recording...")
        self.is_recording = True
        self.audio_data = []
        self.recording_start_time = datetime.now(pytz.timezone('America/Chicago'))

        # Show "Recording started" notification
        self._show_notification("Recording started")

        # Start audio stream
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            callback=self._audio_callback
        )
        self.stream.start()

        # Show indicator in separate thread
        self.indicator = RecordingIndicator(on_click_callback=self._open_recordings_folder)
        self.indicator_thread = threading.Thread(target=self.indicator.show, daemon=True)
        self.indicator_thread.start()

        logger.info("Recording started")

    def stop_recording(self):
        """Stop recording and save file."""
        if not self.is_recording:
            return

        logger.info("Stopping recording...")
        self.is_recording = False

        # Stop stream
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()

        # Hide indicator
        if self.indicator:
            self.indicator.hide()

        # Calculate duration
        recording_end_time = datetime.now(pytz.timezone('America/Chicago'))
        duration = recording_end_time - self.recording_start_time
        duration_minutes = int(duration.total_seconds() / 60)

        # Generate filename: 11Feb2026_15.19CT_91min
        filename = (
            f"{self.recording_start_time.strftime('%d%b%Y_%H.%M')}CT_"
            f"{duration_minutes}min.wav"
        )
        filepath = self.output_dir / filename

        # Save audio
        if self.audio_data:
            audio_array = np.concatenate(self.audio_data, axis=0)
            sf.write(str(filepath), audio_array, self.sample_rate)
            logger.info(f"Recording saved: {filepath}")
            self._show_notification(f"Saved: {duration_minutes}min")
        else:
            logger.warning("No audio data recorded")

    def _audio_callback(self, indata, frames, time_info, status):
        """Audio stream callback."""
        if status:
            logger.warning(f"Audio status: {status}")
        if self.is_recording:
            self.audio_data.append(indata.copy())

    def _show_notification(self, message):
        """Show temporary notification."""
        def show():
            notif = tk.Tk()
            notif.title("")
            notif.overrideredirect(True)
            notif.attributes('-topmost', True)
            notif.attributes('-alpha', 0.9)

            # Position at bottom-right
            width = 200
            height = 60
            screen_width = notif.winfo_screenwidth()
            screen_height = notif.winfo_screenheight()
            x = screen_width - width - 10
            y = screen_height - height - 110

            notif.geometry(f"{width}x{height}+{x}+{y}")

            frame = tk.Frame(notif, bg='#2C3E50')
            frame.pack(fill=tk.BOTH, expand=True)

            label = tk.Label(
                frame,
                text=message,
                bg='#2C3E50',
                fg='white',
                font=('Segoe UI', 11, 'bold'),
                pady=20
            )
            label.pack()

            # Auto-close after 3 seconds
            notif.after(3000, notif.destroy)
            notif.mainloop()

        threading.Thread(target=show, daemon=True).start()

    def _open_recordings_folder(self):
        """Open recordings folder when indicator is clicked."""
        import os
        try:
            os.startfile(self.output_dir)
        except Exception as e:
            logger.error(f"Failed to open folder: {e}")

    def run(self):
        """Run the recorder with keyboard listener."""
        logger.info("Quick Recorder ready! Press Ctrl+Shift+R to start/stop recording")

        def on_activate():
            self.toggle_recording()

        # Set up hotkey
        hotkey = keyboard.HotKey(
            keyboard.HotKey.parse('<ctrl>+<shift>+r'),
            on_activate
        )

        def for_canonical(f):
            return lambda k: f(listener.canonical(k))

        with keyboard.Listener(
            on_press=for_canonical(hotkey.press),
            on_release=for_canonical(hotkey.release)
        ) as listener:
            listener.join()


if __name__ == '__main__':
    print("\n" + "="*60)
    print("Quick Recorder - Keyboard Shortcut Audio Recorder")
    print("="*60)
    print("\nPress Ctrl+Shift+R to start/stop recording")
    print(f"Recordings saved to: {Path.home() / 'Documents' / 'Sound Recordings'}")
    print("\nPress Ctrl+C to exit\n")

    recorder = QuickRecorder()
    try:
        recorder.run()
    except KeyboardInterrupt:
        print("\nExiting...")
