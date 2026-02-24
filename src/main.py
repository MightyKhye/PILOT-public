"""Main entry point for Pilot system tray application."""

import logging
import sys
import threading
from pathlib import Path
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as Item

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meeting_manager import MeetingManager, MeetingState
from src.config import Config
from src.recording_indicator import RecordingIndicator
from src.minimal_notifier import MinimalNotifier

# Configure logging
log_file = Config.LOGS_DIR / "pilot.log"
Config.LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class MeetingListenerApp:
    """System tray application for meeting listener."""

    def __init__(self):
        """Initialize application."""
        self.manager = MeetingManager()
        self.icon: pystray.Icon = None
        self.meeting_in_progress = False
        self._stop_in_progress = False  # Guards against duplicate stop triggers within this process

        # Initialize recording indicator if enabled
        if Config.INDICATOR_ENABLED:
            self.indicator = RecordingIndicator()
            self.indicator.on_click = self.stop_recording
        else:
            self.indicator = None

        # Initialize minimal notifier
        self.minimal_notifier = MinimalNotifier()

        # Create system tray icon
        self.icon_image = self._create_icon()

    def _create_icon(self, color: str = "blue") -> Image.Image:
        """
        Create system tray icon image.

        Args:
            color: Icon color ('blue' for idle, 'red' for recording, 'orange' for processing)

        Returns:
            PIL Image for system tray
        """
        # Create a simple icon (64x64)
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), 'white')
        dc = ImageDraw.Draw(image)

        # Draw detailed brain with folds (black/white only)
        # Main brain outline
        dc.ellipse([16, 12, 48, 52], fill='white', outline='black', width=2)

        # Central fissure
        dc.line([32, 14, 32, 50], fill='black', width=1)

        # Left hemisphere folds
        dc.arc([18, 14, 30, 24], start=180, end=360, fill='black', width=1)
        dc.arc([20, 18, 28, 26], start=180, end=360, fill='black', width=1)
        dc.arc([18, 26, 30, 36], start=180, end=360, fill='black', width=1)
        dc.arc([20, 30, 28, 38], start=180, end=360, fill='black', width=1)
        dc.arc([18, 38, 30, 48], start=180, end=360, fill='black', width=1)

        # Right hemisphere folds
        dc.arc([34, 14, 46, 24], start=180, end=360, fill='black', width=1)
        dc.arc([36, 18, 44, 26], start=180, end=360, fill='black', width=1)
        dc.arc([34, 26, 46, 36], start=180, end=360, fill='black', width=1)
        dc.arc([36, 30, 44, 38], start=180, end=360, fill='black', width=1)
        dc.arc([34, 38, 46, 48], start=180, end=360, fill='black', width=1)

        # Diagonal sulci for detail
        dc.arc([19, 20, 29, 32], start=200, end=340, fill='black', width=1)
        dc.arc([35, 20, 45, 32], start=200, end=340, fill='black', width=1)

        return image

    def _update_icon_state(self, state: MeetingState):
        """Update icon based on meeting state."""
        if not self.icon:
            return

        color_map = {
            MeetingState.IDLE: 'blue',
            MeetingState.RECORDING: 'red',
            MeetingState.PROCESSING: 'orange',
            MeetingState.ERROR: 'gray'
        }

        color = color_map.get(state, 'blue')
        self.icon.icon = self._create_icon(color)

    def _state_change_callback(self, state: MeetingState):
        """Callback for meeting state changes."""
        self._update_icon_state(state)

        # Sync meeting_in_progress flag with actual state
        if state == MeetingState.IDLE:
            self.meeting_in_progress = False
            logger.info("State changed to IDLE - reset meeting_in_progress flag")

        elif state == MeetingState.RECORDING:
            if not self.meeting_in_progress:
                self.meeting_in_progress = True
                logger.info("State changed to RECORDING - set meeting_in_progress flag")

        # Update tooltip
        status_map = {
            MeetingState.IDLE: 'Pilot - Idle',
            MeetingState.RECORDING: 'Pilot - Recording',
            MeetingState.PROCESSING: 'Pilot - Processing',
            MeetingState.ERROR: 'Pilot - Error'
        }

        if self.icon:
            self.icon.title = status_map.get(state, 'Pilot')

        # Update on-screen indicator.
        # is_finalizing via this callback path only works when state CHANGES (RECORDING→PROCESSING).
        # When stop is clicked mid-chunk (state already PROCESSING), this callback never fires for
        # the PROCESSING transition — that case is handled by the direct push in stop_recording().
        if self.indicator:
            chunk_count = len(self.manager.transcriptions)
            is_finalizing = (state == MeetingState.PROCESSING and self.manager._stopping)
            logger.info(f"[CALLBACK] state={state.value}, _stopping={self.manager._stopping}, is_finalizing={is_finalizing}")
            self.indicator.update_state(state, chunk_count, is_finalizing)

    def _toggle_recording(self, icon: pystray.Icon = None):
        """Toggle recording on/off with single click."""
        logger.info("Left-click toggle triggered")

        # Check actual meeting state
        current_state = self.manager.get_state()

        if current_state == MeetingState.IDLE:
            # Idle → Start recording
            logger.info("Left-click: Starting recording (state=IDLE)")
            self.start_recording()
        elif current_state == MeetingState.RECORDING:
            # Recording → Stop recording
            logger.info("Left-click: Stopping recording (state=RECORDING)")
            self.stop_recording()
        elif current_state == MeetingState.PROCESSING:
            # Processing → Do nothing (don't interrupt)
            logger.info("Left-click: Ignoring (state=PROCESSING, please wait)")
            print("Please wait - processing in progress...")
        else:
            logger.warning(f"Left-click: Unknown state {current_state}")

    def start_recording(self, icon: pystray.Icon = None, item: Item = None):
        """Start meeting recording."""
        print("=" * 60)
        print("START RECORDING CLICKED!")
        print("=" * 60)
        logger.info("=" * 60)
        logger.info("START RECORDING MENU CLICKED")
        logger.info("=" * 60)

        if self.meeting_in_progress:
            logger.warning("Meeting already in progress")
            print("Warning: Meeting already in progress")
            return

        logger.info("Starting recording from menu...")

        # Set flag immediately so menu updates
        self.meeting_in_progress = True

        # Start in background thread to avoid blocking UI
        def start_thread():
            logger.info("Start thread running...")
            success = self.manager.start_meeting(callback=self._state_change_callback)
            if success:
                logger.info("Recording started successfully!")
                print("Recording started successfully!")
                # Show minimal notification (removed emoji to avoid encoding issues)
                self.minimal_notifier.notify("Recording started", duration=2)
            else:
                # Reset flag on failure
                self.meeting_in_progress = False
                logger.error("Failed to start recording")
                print("Failed to start recording")
                self.minimal_notifier.notify("Failed to start", duration=3)

        threading.Thread(target=start_thread, daemon=True).start()
        logger.info("Start thread launched")

    def stop_recording(self, icon: pystray.Icon = None, item: Item = None):
        """Stop meeting recording."""
        # Deduplicate: indicator click and tray menu can both fire within 1-2ms of each other.
        # _stop_in_progress is set here (not inside stop_meeting()) so it blocks before the
        # thread is even launched, unlike manager._stopping which is set too late.
        if self._stop_in_progress:
            logger.warning("stop_recording() duplicate call ignored (_stop_in_progress=True)")
            return

        if not self.meeting_in_progress:
            logger.warning("No meeting in progress (flag is False)")
            return

        if self.manager.state == MeetingState.IDLE:
            logger.warning("No meeting in progress (manager is IDLE) - resetting flag")
            self.meeting_in_progress = False
            self.minimal_notifier.notify("No recording in progress", duration=2)
            return

        # Claim the stop slot immediately before launching the thread
        self._stop_in_progress = True
        logger.info(f"[STOP] stop_recording() proceeding (manager state={self.manager.state.value})")

        # IMMEDIATELY push is_finalizing=True to the indicator.
        # We cannot rely on _state_change_callback for this: _update_state() only fires the
        # callback when state CHANGES. If stop is clicked while state is already PROCESSING
        # (mid-chunk Claude/AssemblyAI call), the PROCESSING->PROCESSING "transition" in
        # stop_meeting() fires no callback at all, so is_finalizing would never reach the indicator.
        # Pushing directly here works regardless of current state.
        if self.indicator and self.indicator.window:
            chunk_count = len(self.manager.transcriptions)
            logger.info(f"[STOP] Pushing is_finalizing=True to indicator (chunk_count={chunk_count})")
            self.indicator.update_state(MeetingState.PROCESSING, chunk_count, is_finalizing=True)

        self.minimal_notifier.notify("Stopping recording...", duration=2)

        def stop_thread():
            try:
                summary_path = self.manager.stop_meeting()
                self.meeting_in_progress = False

                if summary_path:
                    logger.info(f"Meeting stopped, summary: {summary_path}")
                    self.minimal_notifier.notify("Meeting summary ready", duration=3)
                    import os
                    try:
                        if sys.platform == 'win32':
                            os.startfile(summary_path)
                            logger.info(f"Opened summary in browser: {summary_path}")
                    except Exception as e:
                        logger.error(f"Failed to open summary: {e}")
                else:
                    logger.error("Failed to generate summary")
                    self.minimal_notifier.notify("Stop completed (no summary)", duration=3)
            finally:
                self._stop_in_progress = False

        threading.Thread(target=stop_thread, daemon=True, name="stop_thread").start()

    def show_status(self, icon: pystray.Icon = None, item: Item = None):
        """Show current status (placeholder for future GUI)."""
        info = self.manager.get_meeting_info()

        status_lines = [
            "Pilot Status",
            "=" * 40,
            f"State: {info['state']}",
        ]

        if self.meeting_in_progress:
            status_lines.extend([
                f"Meeting ID: {info['meeting_id']}",
                f"Duration: {info['duration']}",
                f"Chunks processed: {info['chunks_processed']}",
                f"Analyses: {info['analyses']}"
            ])

        status = "\n".join(status_lines)
        logger.info(f"\n{status}")
        print(f"\n{status}\n")

    def run_status_check(self, icon: pystray.Icon = None, item: Item = None):
        """Run comprehensive status check analysis on meeting history."""
        logger.info("Comprehensive Status Check requested...")
        self.minimal_notifier.notify("Generating comprehensive status report...", duration=3)

        def status_check_thread():
            try:
                # Load meeting history from persistent memory
                meeting_history = self.manager.memory.memory_data.get('meetings', [])

                if not meeting_history:
                    logger.warning("No meeting history available for status check")
                    self.minimal_notifier.notify("No meetings recorded yet", duration=3)
                    return

                # Generate status check using AI analyzer
                result = self.manager.analyzer.generate_status_check(meeting_history)

                # Save status report to file for record-keeping
                try:
                    from datetime import datetime
                    from pathlib import Path

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    status_reports_dir = Config.USER_DOCS_DIR / "status_reports"
                    status_reports_dir.mkdir(exist_ok=True, parents=True)

                    report_file = status_reports_dir / f"status_check_{timestamp}.txt"
                    generated_at = result.get('generated_at', datetime.now().strftime('%B %d, %Y at %I:%M %p CT'))
                    with open(report_file, 'w', encoding='utf-8') as f:
                        f.write(f"PILOT - Project Status Check\n")
                        f.write(f"Generated: {generated_at}\n")
                        f.write(f"Confidence: {result['confidence']}\n")
                        f.write(f"{result['confidence_explanation']}\n")
                        f.write(f"\n{'='*80}\n\n")
                        f.write(result['status_report'])
                        f.write(f"\n\n{'='*80}\n")
                        f.write(f"Report saved: {report_file}\n")

                    logger.info(f"Status report saved to: {report_file}")

                except Exception as save_error:
                    logger.warning(f"Could not save status report to file: {save_error}")
                    # Don't fail the whole operation if file save fails

                # Create status check window
                self._show_status_check_window(result)

                logger.info("Status check completed")

            except Exception as e:
                logger.error(f"Error during status check: {e}")
                import traceback
                traceback.print_exc()
                self.minimal_notifier.notify(f"Status check failed: {str(e)}", duration=5)

        threading.Thread(target=status_check_thread, daemon=True).start()

    def _show_status_check_window(self, result: dict):
        """Show comprehensive status check results in a window."""
        import tkinter as tk
        from tkinter import scrolledtext

        # Create window on main thread
        def create_window():
            window = tk.Tk()
            window.title("Pilot - Project Status Check")
            window.geometry("1000x700")  # Wider window for comprehensive report

            # Header with confidence
            confidence = result['confidence']
            conf_color = {
                'HIGH': '#27ae60',
                'MEDIUM': '#f39c12',
                'LOW': '#e74c3c'
            }.get(confidence, '#95a5a6')

            header = tk.Frame(window, bg='#2C3E50', height=110)
            header.pack(fill=tk.X)

            title_label = tk.Label(
                header,
                text="📊 Project Status Check - Comprehensive Report",
                bg='#2C3E50',
                fg='white',
                font=('Segoe UI', 14, 'bold'),
                pady=5
            )
            title_label.pack()

            # Generation timestamp with timezone
            generated_at = result.get('generated_at', 'Unknown time')
            timestamp_label = tk.Label(
                header,
                text=f"Generated: {generated_at}",
                bg='#2C3E50',
                fg='#ecf0f1',
                font=('Segoe UI', 10),
                pady=2
            )
            timestamp_label.pack()

            conf_label = tk.Label(
                header,
                text=f"Data Confidence: {confidence}",
                bg='#2C3E50',
                fg=conf_color,
                font=('Segoe UI', 11, 'bold'),
                pady=5
            )
            conf_label.pack()

            # Confidence explanation
            conf_exp = tk.Label(
                header,
                text=result['confidence_explanation'],
                bg='#2C3E50',
                fg='#bdc3c7',
                font=('Segoe UI', 9),
                pady=2
            )
            conf_exp.pack()

            # Status report with monospace font for better formatting
            text_area = scrolledtext.ScrolledText(
                window,
                wrap=tk.NONE,  # Don't wrap - preserve formatting
                font=('Consolas', 10),  # Monospace font for structured report
                bg='#f8f9fa',
                fg='#2c3e50',
                padx=15,
                pady=15,
                relief=tk.FLAT,
                spacing1=2,  # Space before paragraphs
                spacing3=2   # Space after paragraphs
            )
            text_area.pack(fill=tk.BOTH, expand=True)

            # Insert report with syntax highlighting for headers and urgent items
            report_text = result['status_report']
            text_area.insert(tk.END, report_text)

            # Configure text tags for highlighting
            text_area.tag_configure("urgent", foreground="#e74c3c", font=('Consolas', 10, 'bold'))
            text_area.tag_configure("header", foreground="#2c3e50", font=('Consolas', 11, 'bold'))
            text_area.tag_configure("separator", foreground="#95a5a6")

            # Highlight [URGENT] items
            start_pos = "1.0"
            while True:
                pos = text_area.search("[URGENT]", start_pos, tk.END)
                if not pos:
                    break
                end_pos = f"{pos}+8c"
                text_area.tag_add("urgent", pos, end_pos)
                start_pos = end_pos

            # Highlight section headers (lines with ═══)
            lines = report_text.split('\n')
            for i, line in enumerate(lines, 1):
                if '═══' in line:
                    text_area.tag_add("separator", f"{i}.0", f"{i}.end")
                elif line.strip().endswith(':') and len(line.strip()) > 10:
                    # Header lines (end with : and are substantial)
                    if i > 1 and '═══' in lines[i-2] if i-2 < len(lines) else False:
                        text_area.tag_add("header", f"{i}.0", f"{i}.end")

            text_area.config(state=tk.DISABLED)

            # Footer with metrics
            footer = tk.Frame(window, bg='#34495e', height=45)
            footer.pack(fill=tk.X)

            data_quality = result.get('data_quality', {})
            footer_text = (
                f"Analysis based on: {data_quality.get('total_meetings', 0)} total meetings • "
                f"Last 3 meetings reviewed • {data_quality.get('action_items_count', 0)} action items • "
                f"{data_quality.get('decisions_count', 0)} decisions"
            )

            footer_label = tk.Label(
                footer,
                text=footer_text,
                bg='#34495e',
                fg='#bdc3c7',
                font=('Segoe UI', 9),
                pady=12
            )
            footer_label.pack()

            # Add button bar
            button_frame = tk.Frame(window, bg='#ecf0f1', height=50)
            button_frame.pack(fill=tk.X)

            # Copy to clipboard button
            def copy_to_clipboard():
                window.clipboard_clear()
                window.clipboard_append(result['status_report'])
                window.update()
                # Flash button to show it worked
                copy_btn.config(text="✓ Copied!")
                window.after(1500, lambda: copy_btn.config(text="Copy to Clipboard"))

            copy_btn = tk.Button(
                button_frame,
                text="Copy to Clipboard",
                command=copy_to_clipboard,
                bg='#3498db',
                fg='white',
                font=('Segoe UI', 10),
                padx=20,
                pady=8,
                relief=tk.FLAT,
                cursor='hand2'
            )
            copy_btn.pack(side=tk.LEFT, padx=10, pady=10)

            # Close button
            close_btn = tk.Button(
                button_frame,
                text="Close",
                command=window.destroy,
                bg='#95a5a6',
                fg='white',
                font=('Segoe UI', 10),
                padx=20,
                pady=8,
                relief=tk.FLAT,
                cursor='hand2'
            )
            close_btn.pack(side=tk.RIGHT, padx=10, pady=10)

            window.mainloop()

        # Run on main thread
        create_window()

    def query_meetings(self, icon: pystray.Icon = None, item: Item = None):
        """Allow user to ask questions about meetings."""
        import subprocess

        def show_query_window():
            # Use Windows native input box via PowerShell (guaranteed to work)
            powershell_cmd = '''
Add-Type -AssemblyName Microsoft.VisualBasic
[Microsoft.VisualBasic.Interaction]::InputBox("What do you want to know about your meetings?`n`nExamples:`n• When were dates offered to McKesson?`n• What action items are assigned to Ian?", "Query Meetings - Pilot")
'''
            try:
                result = subprocess.run(
                    ['powershell', '-Command', powershell_cmd],
                    capture_output=True,
                    text=True,
                    timeout=120
                )

                question = result.stdout.strip()

                if not question:
                    logger.info("Query cancelled or empty")
                    return

                logger.info(f"Query submitted: '{question}'")

                # Process query in background
                def process_query():
                    try:
                        meeting_history = self.manager.memory.memory_data.get('meetings', [])

                        if not meeting_history:
                            self.minimal_notifier.notify("No meetings recorded yet", duration=3)
                            return

                        # Get answer from AI
                        result = self.manager.analyzer.query_meetings(question, meeting_history)

                        # Show answer window
                        self._show_query_result(question, result)

                    except Exception as e:
                        logger.error(f"Error processing query: {e}")
                        self.minimal_notifier.notify(f"Query failed: {str(e)}", duration=5)

                threading.Thread(target=process_query, daemon=True).start()
                self.minimal_notifier.notify("Searching meetings...", duration=2)

            except subprocess.TimeoutExpired:
                logger.warning("Query input timed out")
            except Exception as e:
                logger.error(f"Error showing query window: {e}")

        # Run on main thread
        show_query_window()

    def _show_query_result(self, question: str, result: dict):
        """Show query result window."""
        import tkinter as tk
        from tkinter import scrolledtext

        def create_window():
            window = tk.Tk()
            window.title("Query Result")
            window.geometry("600x450")

            # Header with question
            header = tk.Frame(window, bg='#2C3E50')
            header.pack(fill=tk.X)

            question_label = tk.Label(
                header,
                text=f"Q: {question}",
                bg='#2C3E50',
                fg='white',
                font=('Segoe UI', 11, 'bold'),
                wraplength=550,
                justify='left',
                padx=20,
                pady=15
            )
            question_label.pack(anchor='w')

            # Confidence indicator
            confidence = result['confidence']
            conf_color = {
                'HIGH': '#27ae60',
                'MEDIUM': '#f39c12',
                'LOW': '#e74c3c'
            }.get(confidence, '#95a5a6')

            conf_frame = tk.Frame(header, bg='#2C3E50')
            conf_frame.pack(fill=tk.X, padx=20, pady=(0, 15))

            conf_label = tk.Label(
                conf_frame,
                text=f"Confidence: {confidence}",
                bg='#2C3E50',
                fg=conf_color,
                font=('Segoe UI', 9, 'bold')
            )
            conf_label.pack(side=tk.LEFT)

            # Answer text
            text_area = scrolledtext.ScrolledText(
                window,
                wrap=tk.WORD,
                font=('Segoe UI', 11),
                bg='#ecf0f1',
                fg='#2c3e50',
                padx=20,
                pady=20,
                relief=tk.FLAT
            )
            text_area.pack(fill=tk.BOTH, expand=True)
            text_area.insert(tk.END, result['answer'])
            text_area.config(state=tk.DISABLED)

            # Footer
            footer = tk.Frame(window, bg='#34495e', height=40)
            footer.pack(fill=tk.X)

            sources = result.get('sources', [])
            footer_text = f"Searched {len(sources)} meetings"

            footer_label = tk.Label(
                footer,
                text=footer_text,
                bg='#34495e',
                fg='#bdc3c7',
                font=('Segoe UI', 9),
                pady=10
            )
            footer_label.pack()

            window.mainloop()

        create_window()

    def open_meetings_folder(self, icon: pystray.Icon = None, item: Item = None):
        """Open meetings folder in file explorer."""
        import subprocess
        import os

        meetings_dir = Config.MEETINGS_DIR
        meetings_dir.mkdir(exist_ok=True)

        try:
            if sys.platform == 'win32':
                os.startfile(meetings_dir)
            elif sys.platform == 'darwin':
                subprocess.run(['open', meetings_dir])
            else:
                subprocess.run(['xdg-open', meetings_dir])
        except Exception as e:
            logger.error(f"Failed to open meetings folder: {e}")

    def upload_recording(self, icon: pystray.Icon = None, item: Item = None):
        """Upload and process an audio recording."""
        import tkinter as tk
        from tkinter import filedialog
        import threading

        def upload_thread():
            try:
                # Create file dialog
                root = tk.Tk()
                root.withdraw()  # Hide main window
                root.attributes('-topmost', True)  # Bring to front

                # Open file picker
                file_path = filedialog.askopenfilename(
                    title="Select Meeting Recording",
                    filetypes=[
                        ("Audio Files", "*.wav *.m4a *.mp3 *.mp4 *.aac *.flac *.ogg"),
                        ("iPhone Voice Memos", "*.m4a"),
                        ("All Files", "*.*")
                    ]
                )

                root.destroy()

                if not file_path:
                    logger.info("Upload cancelled")
                    return

                logger.info(f"Processing uploaded file: {file_path}")
                self.minimal_notifier.notify("Processing audio file...", duration=3)

                # Process the file
                from pathlib import Path
                import sys
                sys.path.insert(0, str(Path(__file__).parent.parent))

                from process_audio_file import process_audio_file
                process_audio_file(file_path)

                self.minimal_notifier.notify("Audio processed successfully!", duration=3)

            except Exception as e:
                logger.error(f"Error processing upload: {e}", exc_info=True)
                self.minimal_notifier.notify("Failed to process audio", duration=3)

        # Run in background thread
        threading.Thread(target=upload_thread, daemon=True).start()

    def exit_app(self, icon: pystray.Icon = None, item: Item = None):
        """Exit application with proper cleanup."""
        logger.info("Exiting application...")

        # Stop recording if in progress (blocking call)
        if self.meeting_in_progress:
            logger.info("Stopping active recording before exit...")
            self.stop_recording()
            # Give stop_recording thread time to complete
            import time
            time.sleep(2)

        # Stop indicator
        if self.indicator:
            logger.info("Stopping recording indicator...")
            self.indicator.stop()

        # Cleanup manager (will join all threads with timeout)
        logger.info("Cleaning up meeting manager...")
        self.manager.cleanup()

        # Stop system tray icon
        if self.icon:
            logger.info("Stopping system tray icon...")
            self.icon.stop()

        logger.info("Application exited successfully")

    def _create_menu(self):
        """
        Create system tray menu.

        Menu enabled state: Uses meeting_in_progress flag (reliable on Windows)
        Left-click behavior: Uses get_state() via default parameter
        - When IDLE: left-click triggers Start Recording
        - When RECORDING: left-click triggers Stop Recording
        - When PROCESSING: no default item, left-click does nothing
        """
        return pystray.Menu(
            Item(
                'Start Recording',
                self.start_recording,
                enabled=lambda item: not self.meeting_in_progress,
                default=lambda item: self.manager.get_state() == MeetingState.IDLE
            ),
            Item(
                'Stop Recording',
                self.stop_recording,
                enabled=lambda item: self.meeting_in_progress,
                default=lambda item: self.manager.get_state() == MeetingState.RECORDING
            ),
            Item('Status Check', self.run_status_check),
            Item('Query Meetings', self.query_meetings),
            pystray.Menu.SEPARATOR,
            Item('Upload Meeting Recording', self.upload_recording),
            Item('Open Meetings Folder', self.open_meetings_folder),
            pystray.Menu.SEPARATOR,
            Item('Exit', self.exit_app)
        )

    def run(self):
        """Run the system tray application."""
        logger.info("Starting Pilot application...")

        # Validate configuration
        errors = Config.validate()
        if errors:
            error_msg = "Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
            logger.error(error_msg)
            print(f"\n{error_msg}\n")
            print("Please set up your .env file with API keys.")
            print("See .env.example for the template.\n")
            return

        logger.info("Configuration valid")

        # Start on-screen indicator if enabled
        if self.indicator:
            self.indicator.start()
            logger.info("On-screen indicator started")

        # Sync meeting_in_progress flag with actual manager state
        if self.manager.state == MeetingState.IDLE:
            self.meeting_in_progress = False
            logger.info("Initial state sync: No meeting in progress")
        else:
            self.meeting_in_progress = True
            logger.info(f"Initial state sync: Meeting in progress (state: {self.manager.state})")

        # Create system tray icon
        # Left-click = Activates default MenuItem (Start/Stop based on state)
        # Right-click = Show full menu
        self.icon = pystray.Icon(
            'remshadow',
            self.icon_image,
            'Pilot - Idle',
            menu=self._create_menu()
        )

        # Run (this blocks until exit)
        logger.info("System tray icon created, running...")
        print("\n" + "=" * 60)
        print("Pilot started!")
        print("=" * 60)
        print("\nLook for the microphone icon in your system tray.")
        print("Right-click the icon to start recording.\n")
        print("Logs are saved to:", log_file)
        print("=" * 60 + "\n")

        try:
            self.icon.run()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            self.exit_app()


def main():
    """Main entry point."""
    try:
        app = MeetingListenerApp()
        app.run()
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        print(f"\nError: {e}")
        print("Check the log file for details:", Config.LOGS_DIR / "remshadow.log")
        sys.exit(1)


if __name__ == '__main__':
    main()
