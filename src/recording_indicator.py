"""On-screen recording indicator widget - simplified and reliable."""

import tkinter as tk
import threading
import logging
from datetime import datetime
from typing import Optional

from .meeting_manager import MeetingState

logger = logging.getLogger(__name__)


class RecordingIndicator:
    """Persistent on-screen indicator showing recording state."""

    def __init__(self):
        """Initialize the recording indicator."""
        self.window: Optional[tk.Tk] = None
        self.state = MeetingState.IDLE
        self.meeting_start_time: Optional[datetime] = None
        self.chunk_count = 0

        # UI elements
        self.canvas: Optional[tk.Canvas] = None

        # Threading
        self.running = False
        self.update_thread: Optional[threading.Thread] = None

        # Click callback (set by caller; called on left-click to stop recording)
        self.on_click = None

        # Visual state
        self.blink_state = False
        self.is_expanded = False
        self.frozen_time_text: Optional[str] = None  # Set when recording stops; cleared on IDLE
        self.is_finalizing = False  # True only during final summary generation (not chunk PROCESSING)

        # Dimensions
        self.collapsed_width = 40
        self.expanded_width = 170
        self.height = 70

        logger.info("RecordingIndicator initialized")

    def start(self):
        """Start the indicator in a separate thread."""
        if self.running:
            return

        self.running = True
        self.update_thread = threading.Thread(target=self._run_indicator, daemon=True)
        self.update_thread.start()
        logger.info("Recording indicator thread started")

    def stop(self):
        """Stop and destroy the indicator."""
        if not self.running:
            return

        self.running = False
        if self.window:
            try:
                self.window.after(0, self._destroy_window)
            except:
                pass
        logger.info("Recording indicator stopped")

    def _destroy_window(self):
        """Destroy the window safely."""
        try:
            if self.window:
                self.window.quit()
                self.window.destroy()
                self.window = None
        except Exception as e:
            logger.error(f"Error destroying window: {e}")

    def update_state(self, state: MeetingState, chunk_count: int = 0, is_finalizing: bool = False):
        """Update indicator state (thread-safe)."""
        if not self.window:
            return

        try:
            self.window.after(0, self._update_ui, state, chunk_count, is_finalizing)
        except Exception as e:
            logger.error(f"Error scheduling state update: {e}")

    def _run_indicator(self):
        """Main loop for indicator."""
        try:
            self.window = tk.Tk()
            self._create_window()
            self._position_window()
            self.window.withdraw()  # Start hidden
            self._blink_loop()  # Start blink timer
            self.window.mainloop()
        except Exception as e:
            logger.error(f"Error in indicator main loop: {e}", exc_info=True)
        finally:
            self.running = False

    def _create_window(self):
        """Create the indicator window."""
        # Window config
        self.window.title("Pilot")
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)

        try:
            self.window.attributes('-alpha', 0.95)
        except:
            pass

        bg_color = '#1a1a1a'
        self.window.configure(bg=bg_color)

        # Canvas for drawing
        self.canvas = tk.Canvas(
            self.window,
            width=self.collapsed_width,
            height=self.height,
            bg=bg_color,
            highlightthickness=0
        )
        self.canvas.pack()

        # Hover events
        self.canvas.bind('<Enter>', self._on_hover_enter)
        self.canvas.bind('<Leave>', self._on_hover_leave)
        self.window.bind('<Enter>', self._on_hover_enter)
        self.window.bind('<Leave>', self._on_hover_leave)

        # Left-click → stop recording (indicator is only visible during recording)
        self.canvas.bind('<Button-1>', self._on_left_click)
        self.window.bind('<Button-1>', self._on_left_click)

    def _position_window(self):
        """Position at right edge."""
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()

        x = screen_width - self.collapsed_width
        y = (screen_height // 2) - (self.height // 2)

        self.window.geometry(f"{self.collapsed_width}x{self.height}+{x}+{y}")
        logger.info(f"Positioned at x={x}, y={y}")

    def _update_ui(self, state: MeetingState, chunk_count: int, is_finalizing: bool = False):
        """Update UI based on state."""
        try:
            logger.info(f"==> Indicator state update: {state.value}, chunks: {chunk_count}, finalizing: {is_finalizing}")

            old_state = self.state
            self.state = state
            self.chunk_count = chunk_count
            self.is_finalizing = is_finalizing

            # Show/hide based on state
            if state == MeetingState.IDLE:
                self.window.withdraw()
                self.window.update_idletasks()
                self.meeting_start_time = None
                self.frozen_time_text = None
                logger.info("Indicator hidden (IDLE)")
            else:
                self.window.deiconify()
                self.window.lift()
                logger.info(f"Indicator visible ({state.value})")

                if state == MeetingState.RECORDING:
                    if not self.meeting_start_time:
                        self.meeting_start_time = datetime.now()
                    self.frozen_time_text = None  # Resume live timer
                elif state == MeetingState.PROCESSING:
                    # Freeze the timer only when finalizing (stop clicked), NOT during
                    # mid-recording chunk PROCESSING. is_finalizing=True only when
                    # stop_meeting() is actively running (_stopping flag in MeetingManager).
                    if self.is_finalizing and self.meeting_start_time and self.frozen_time_text is None:
                        elapsed = datetime.now() - self.meeting_start_time
                        m = int(elapsed.total_seconds() // 60)
                        s = int(elapsed.total_seconds() % 60)
                        self.frozen_time_text = f"{m:02d}:{s:02d}"

            # Redraw
            self._draw()

        except Exception as e:
            logger.error(f"Error updating UI: {e}", exc_info=True)

    def _draw(self):
        """Draw the indicator."""
        if not self.canvas:
            return

        # Don't draw if idle - window should be hidden
        if self.state == MeetingState.IDLE:
            return

        try:
            self.canvas.delete("all")

            width = self.canvas.winfo_width()
            height = self.canvas.winfo_height()

            if self.is_expanded:
                # Expanded view
                # Draw background
                self.canvas.create_rectangle(0, 0, width, height, fill='#2C3E50', outline='')

                # Draw dot
                dot_color = self._get_dot_color()
                self.canvas.create_oval(10, 10, 25, 25, fill=dot_color, outline=dot_color)

                # Draw text
                self.canvas.create_text(
                    40, 20,
                    text="Pilot",
                    fill='white',
                    font=('Segoe UI', 10, 'bold'),
                    anchor='w'
                )

                # Draw time - frozen during PROCESSING, live during RECORDING
                if self.frozen_time_text:
                    time_text = self.frozen_time_text
                elif self.meeting_start_time:
                    elapsed = datetime.now() - self.meeting_start_time
                    m = int(elapsed.total_seconds() // 60)
                    s = int(elapsed.total_seconds() % 60)
                    time_text = f"{m:02d}:{s:02d}"
                else:
                    time_text = None

                if time_text:
                    self.canvas.create_text(
                        40, 45,
                        text=time_text,
                        fill='#BDC3C7',
                        font=('Segoe UI', 9),
                        anchor='w'
                    )
            else:
                # Collapsed view - just the dot
                dot_color = self._get_dot_color()
                self.canvas.create_oval(10, 25, 30, 45, fill=dot_color, outline=dot_color, width=2)

            self.canvas.update()

        except Exception as e:
            logger.error(f"Error drawing: {e}")

    def _get_dot_color(self):
        """Get dot color based on state and blink."""
        if self.state == MeetingState.RECORDING:
            # Slow blink: bright red ↔ dark red
            return '#FF1744' if self.blink_state else '#880E4F'
        elif self.state == MeetingState.PROCESSING:
            # Rapid blink: bright yellow ↔ dark yellow (signals "working, not frozen")
            return '#F1C40F' if self.blink_state else '#7D6608'
        elif self.state == MeetingState.ERROR:
            return '#7F8C8D'  # Gray
        else:
            return '#E74C3C'  # Red

    def _blink_loop(self):
        """Blink the indicator. 500ms during recording, 250ms during processing."""
        if not self.running or not self.window:
            return

        try:
            if self.state != MeetingState.IDLE:
                self.blink_state = not self.blink_state
                self._draw()
            interval = 250 if (self.state == MeetingState.PROCESSING and self.is_finalizing) else 500
            self.window.after(interval, self._blink_loop)
        except Exception as e:
            logger.error(f"Error in blink loop: {e}")

    def _on_left_click(self, event):
        """Fire the stop callback when the indicator is clicked."""
        if self.on_click:
            threading.Thread(target=self.on_click, daemon=True, name="IndicatorClick").start()

    def _on_hover_enter(self, event):
        """Expand on hover."""
        try:
            if not self.is_expanded and self.state != MeetingState.IDLE:
                logger.info("Expanding on hover")
                self.is_expanded = True
                self._resize(self.expanded_width)
        except Exception as e:
            logger.error(f"Error on hover enter: {e}")

    def _on_hover_leave(self, event):
        """Collapse when leaving."""
        try:
            if self.is_expanded:
                logger.info("Collapsing after hover")
                self.is_expanded = False
                self._resize(self.collapsed_width)
        except Exception as e:
            logger.error(f"Error on hover leave: {e}")

    def _resize(self, new_width):
        """Resize window to new width."""
        try:
            screen_width = self.window.winfo_screenwidth()
            current_y = self.window.winfo_y()

            x = screen_width - new_width
            self.window.geometry(f"{new_width}x{self.height}+{x}+{current_y}")

            # Resize canvas
            self.canvas.config(width=new_width)
            self.canvas.update()

            self._draw()

        except Exception as e:
            logger.error(f"Error resizing: {e}")
