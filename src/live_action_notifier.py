"""
Live Action Item Notifier - Real-time notifications during meetings.

Monitors streaming transcription and shows notifications when action items
are assigned to the user.
"""

import tkinter as tk
from tkinter import ttk
import threading
import queue
import re
import logging
from datetime import datetime
from typing import Optional, Callable, Dict, List
import time

logger = logging.getLogger(__name__)


class ActionItemNotification:
    """Represents a detected action item notification."""

    def __init__(self, text: str, action: str, assignee: str, speaker: str = "Unknown", timestamp: datetime = None):
        self.text = text
        self.action = action
        self.assignee = assignee
        self.speaker = speaker
        self.timestamp = timestamp or datetime.now()
        self.status = "pending"  # pending, confirmed, ignored
        self.id = f"{int(self.timestamp.timestamp())}_{hash(text) % 10000}"


class NotificationWindow:
    """Semi-transparent notification overlay window."""

    def __init__(self, notification: ActionItemNotification, duration: int, auto_approve: bool,
                 on_confirm: Callable, on_ignore: Callable, my_name: str):
        self.notification = notification
        self.duration = duration
        self.auto_approve = auto_approve
        self.on_confirm = on_confirm
        self.on_ignore = on_ignore
        self.my_name = my_name
        self.window = None
        self.timer_label = None
        self.remaining_time = duration
        self.timer_thread = None
        self.dismissed = False

    def show(self):
        """Show the notification window."""
        try:
            self.window = tk.Toplevel()
            self.window.title("Action Item")

            # Window configuration
            self.window.overrideredirect(True)  # No title bar
            self.window.attributes('-topmost', True)  # Always on top
            self.window.attributes('-alpha', 0.95)  # Semi-transparent

            # Position in bottom-right corner
            window_width = 420
            window_height = 200
            screen_width = self.window.winfo_screenwidth()
            screen_height = self.window.winfo_screenheight()
            x = screen_width - window_width - 20
            y = screen_height - window_height - 60  # Above taskbar

            self.window.geometry(f"{window_width}x{window_height}+{x}+{y}")

            # Main frame with border
            main_frame = tk.Frame(self.window, bg='#2C3E50', bd=2, relief=tk.RAISED)
            main_frame.pack(fill=tk.BOTH, expand=True)

            # Header
            header = tk.Frame(main_frame, bg='#E74C3C', height=40)
            header.pack(fill=tk.X)

            timestamp_str = self.notification.timestamp.strftime("%I:%M %p CT")
            header_label = tk.Label(
                header,
                text=f"🎯 Action Item Detected ({timestamp_str})",
                bg='#E74C3C',
                fg='white',
                font=('Segoe UI', 11, 'bold'),
                pady=8
            )
            header_label.pack()

            # Content area
            content = tk.Frame(main_frame, bg='white', padx=15, pady=15)
            content.pack(fill=tk.BOTH, expand=True)

            # Quote
            quote_frame = tk.Frame(content, bg='#ECF0F1', bd=1, relief=tk.SOLID)
            quote_frame.pack(fill=tk.X, pady=(0, 10))

            quote_text = f"{self.notification.speaker}: \"{self.notification.text}\""
            if len(quote_text) > 150:
                quote_text = quote_text[:147] + "..."

            quote_label = tk.Label(
                quote_frame,
                text=quote_text,
                bg='#ECF0F1',
                fg='#2C3E50',
                font=('Segoe UI', 9, 'italic'),
                wraplength=380,
                justify=tk.LEFT,
                padx=10,
                pady=8
            )
            quote_label.pack()

            # Action
            action_label = tk.Label(
                content,
                text=f"ACTION: {self.notification.action}",
                bg='white',
                fg='#2C3E50',
                font=('Segoe UI', 10, 'bold'),
                anchor=tk.W
            )
            action_label.pack(fill=tk.X, pady=(0, 5))

            # Assignee (highlight user's name)
            assignee_text = f"ASSIGNED TO: {self.notification.assignee}"
            if self.my_name.lower() in self.notification.assignee.lower():
                assignee_text += " (YOU)"

            assignee_label = tk.Label(
                content,
                text=assignee_text,
                bg='white',
                fg='#E74C3C' if 'YOU' in assignee_text else '#2C3E50',
                font=('Segoe UI', 10, 'bold'),
                anchor=tk.W
            )
            assignee_label.pack(fill=tk.X, pady=(0, 10))

            # Button frame
            button_frame = tk.Frame(content, bg='white')
            button_frame.pack(fill=tk.X)

            # Got it button
            got_it_btn = tk.Button(
                button_frame,
                text="✓ Got it",
                command=self._on_confirm_click,
                bg='#27AE60',
                fg='white',
                font=('Segoe UI', 10, 'bold'),
                padx=20,
                pady=8,
                relief=tk.FLAT,
                cursor='hand2',
                activebackground='#229954'
            )
            got_it_btn.pack(side=tk.LEFT, padx=(0, 10))

            # Ignore button
            ignore_btn = tk.Button(
                button_frame,
                text="✗ Ignore",
                command=self._on_ignore_click,
                bg='#95A5A6',
                fg='white',
                font=('Segoe UI', 10),
                padx=20,
                pady=8,
                relief=tk.FLAT,
                cursor='hand2',
                activebackground='#7F8C8D'
            )
            ignore_btn.pack(side=tk.LEFT)

            # Timer label
            if self.auto_approve:
                self.timer_label = tk.Label(
                    button_frame,
                    text=f"Auto: {self.remaining_time}s",
                    bg='white',
                    fg='#7F8C8D',
                    font=('Segoe UI', 9)
                )
                self.timer_label.pack(side=tk.RIGHT)

                # Start countdown timer
                self.timer_thread = threading.Thread(target=self._countdown_timer, daemon=True)
                self.timer_thread.start()

            # Fade in animation
            self._fade_in()

            logger.info(f"Notification shown: {self.notification.action}")

        except Exception as e:
            logger.error(f"Error showing notification window: {e}")
            import traceback
            traceback.print_exc()

    def _fade_in(self):
        """Fade in animation."""
        try:
            alpha = 0.0
            while alpha < 0.95 and self.window and self.window.winfo_exists():
                alpha += 0.05
                self.window.attributes('-alpha', alpha)
                time.sleep(0.02)
        except:
            pass

    def _countdown_timer(self):
        """Countdown timer for auto-approve."""
        try:
            while self.remaining_time > 0 and not self.dismissed:
                time.sleep(1)
                self.remaining_time -= 1
                if self.timer_label and not self.dismissed:
                    try:
                        self.timer_label.config(text=f"Auto: {self.remaining_time}s")
                    except:
                        break

            # Auto-approve if not dismissed
            if not self.dismissed and self.auto_approve:
                logger.info(f"Auto-approving action item: {self.notification.action}")
                self.window.after(0, self._on_confirm_click)

        except Exception as e:
            logger.error(f"Error in countdown timer: {e}")

    def _on_confirm_click(self):
        """Handle 'Got it' button click."""
        if self.dismissed:
            return
        self.dismissed = True
        logger.info(f"Action item confirmed: {self.notification.action}")
        self.on_confirm(self.notification)
        self._close()

    def _on_ignore_click(self):
        """Handle 'Ignore' button click."""
        if self.dismissed:
            return
        self.dismissed = True
        logger.info(f"Action item ignored: {self.notification.action}")
        self.on_ignore(self.notification)
        self._close()

    def _close(self):
        """Close the notification window with fade out."""
        try:
            # Fade out
            alpha = 0.95
            while alpha > 0 and self.window and self.window.winfo_exists():
                alpha -= 0.1
                try:
                    self.window.attributes('-alpha', alpha)
                    time.sleep(0.02)
                except:
                    break

            if self.window:
                self.window.destroy()
        except Exception as e:
            logger.error(f"Error closing notification: {e}")


class LiveActionNotifier:
    """Monitors live transcription and shows action item notifications."""

    def __init__(self, my_name: str, name_variations: List[str] = None,
                 notification_duration: int = 5, auto_approve: bool = True,
                 enabled: bool = True):
        """
        Initialize live action notifier.

        Args:
            my_name: User's name to detect
            name_variations: Alternative spellings/pronunciations
            notification_duration: How long to show notification (seconds)
            auto_approve: Auto-approve if no interaction
            enabled: Whether notifications are enabled
        """
        self.my_name = my_name
        self.name_variations = name_variations or [my_name]
        self.notification_duration = notification_duration
        self.auto_approve = auto_approve
        self.enabled = enabled

        # Notification queue
        self.notification_queue = queue.Queue()
        self.current_notification_window = None
        self.processing_notifications = False

        # Detected items
        self.confirmed_items = []
        self.ignored_items = []
        self.pending_items = []

        # Pattern compilation
        self._compile_patterns()

        logger.info(f"Live Action Notifier initialized for: {my_name}")
        logger.info(f"Name variations: {', '.join(self.name_variations)}")

    def _compile_patterns(self):
        """Compile regex patterns for action detection."""
        # Create name pattern matching any variation
        name_pattern = '|'.join(re.escape(name) for name in self.name_variations)

        # Action patterns
        self.patterns = [
            # "[USER], can you..."
            re.compile(rf"\b({name_pattern}),?\s+can\s+you\s+(.+?)(?:\.|$)", re.IGNORECASE),
            # "[USER] needs to..."
            re.compile(rf"\b({name_pattern})\s+needs?\s+to\s+(.+?)(?:\.|$)", re.IGNORECASE),
            # "[USER] will..."
            re.compile(rf"\b({name_pattern})\s+will\s+(.+?)(?:\.|$)", re.IGNORECASE),
            # "[USER] should..."
            re.compile(rf"\b({name_pattern})\s+should\s+(.+?)(?:\.|$)", re.IGNORECASE),
            # "[USER], please..."
            re.compile(rf"\b({name_pattern}),?\s+please\s+(.+?)(?:\.|$)", re.IGNORECASE),
            # "Action for [USER]:"
            re.compile(rf"action\s+for\s+({name_pattern}):\s*(.+?)(?:\.|$)", re.IGNORECASE),
            # "Have [USER]..."
            re.compile(rf"have\s+({name_pattern})\s+(.+?)(?:\.|$)", re.IGNORECASE),
            # "Ask [USER] to..."
            re.compile(rf"ask\s+({name_pattern})\s+to\s+(.+?)(?:\.|$)", re.IGNORECASE),
            # "Could [USER]..."
            re.compile(rf"could\s+({name_pattern})\s+(.+?)(?:\.|$)", re.IGNORECASE),
        ]

    def enable(self):
        """Enable notifications."""
        self.enabled = True
        logger.info("Live action notifications enabled")

    def disable(self):
        """Disable notifications."""
        self.enabled = False
        logger.info("Live action notifications disabled")

    def is_enabled(self):
        """Check if notifications are enabled."""
        return self.enabled

    def process_transcript_chunk(self, text: str, speaker: str = "Unknown"):
        """
        Process a chunk of transcript text for action items.

        Args:
            text: Transcript text to analyze
            speaker: Who said it (if available)
        """
        if not self.enabled:
            return

        # Check each pattern
        for pattern in self.patterns:
            matches = pattern.finditer(text)
            for match in matches:
                detected_name = match.group(1)
                action_text = match.group(2).strip()

                # Clean up action text
                action_text = self._clean_action_text(action_text)

                if len(action_text) < 5:  # Too short, probably not a real action
                    continue

                # Create notification
                notification = ActionItemNotification(
                    text=text.strip(),
                    action=action_text,
                    assignee=detected_name,
                    speaker=speaker,
                    timestamp=datetime.now()
                )

                # Add to queue
                self.notification_queue.put(notification)
                self.pending_items.append(notification)

                logger.info(f"Action item detected: {action_text} -> {detected_name}")

                # Start processing if not already
                if not self.processing_notifications:
                    self._start_notification_processor()

                # Only detect once per text chunk
                break

    def _clean_action_text(self, text: str) -> str:
        """Clean up extracted action text."""
        # Remove trailing punctuation
        text = text.rstrip('.,!?;:')

        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]

        return text

    def _start_notification_processor(self):
        """Start processing notifications from queue."""
        if self.processing_notifications:
            return

        self.processing_notifications = True
        thread = threading.Thread(target=self._notification_processor_loop, daemon=True)
        thread.start()

    def _notification_processor_loop(self):
        """Process notifications from queue one at a time."""
        try:
            while True:
                try:
                    # Get next notification (with timeout to allow exit)
                    notification = self.notification_queue.get(timeout=1.0)

                    # Show notification on main thread
                    self._show_notification_sync(notification)

                    # Wait for current notification to be dismissed
                    while self.current_notification_window is not None:
                        time.sleep(0.1)

                except queue.Empty:
                    # Check if we should exit
                    if self.notification_queue.empty():
                        break

        except Exception as e:
            logger.error(f"Error in notification processor: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.processing_notifications = False

    def _show_notification_sync(self, notification: ActionItemNotification):
        """Show notification window (thread-safe)."""
        try:
            # Create window on main thread
            def create_window():
                self.current_notification_window = NotificationWindow(
                    notification=notification,
                    duration=self.notification_duration,
                    auto_approve=self.auto_approve,
                    on_confirm=self._on_confirm,
                    on_ignore=self._on_ignore,
                    my_name=self.my_name
                )
                self.current_notification_window.show()

            # Schedule on main thread if possible
            try:
                import tkinter as tk
                tk._default_root.after(0, create_window)
            except:
                # Fallback: create directly (may cause issues on some systems)
                create_window()

        except Exception as e:
            logger.error(f"Error showing notification: {e}")

    def _on_confirm(self, notification: ActionItemNotification):
        """Handle notification confirmation."""
        notification.status = "confirmed"
        self.confirmed_items.append(notification)
        if notification in self.pending_items:
            self.pending_items.remove(notification)
        self.current_notification_window = None
        logger.info(f"Action confirmed: {notification.action}")

    def _on_ignore(self, notification: ActionItemNotification):
        """Handle notification ignore."""
        notification.status = "ignored"
        self.ignored_items.append(notification)
        if notification in self.pending_items:
            self.pending_items.remove(notification)
        self.current_notification_window = None
        logger.info(f"Action ignored: {notification.action}")

    def get_confirmed_items(self) -> List[ActionItemNotification]:
        """Get all confirmed action items."""
        return self.confirmed_items.copy()

    def get_ignored_items(self) -> List[ActionItemNotification]:
        """Get all ignored action items."""
        return self.ignored_items.copy()

    def get_summary(self) -> Dict:
        """Get summary of detected action items."""
        return {
            'confirmed': len(self.confirmed_items),
            'ignored': len(self.ignored_items),
            'total_detected': len(self.confirmed_items) + len(self.ignored_items),
            'confirmed_items': self.confirmed_items,
            'ignored_items': self.ignored_items
        }

    def reset(self):
        """Reset all detected items (called at meeting start)."""
        self.confirmed_items = []
        self.ignored_items = []
        self.pending_items = []
        logger.info("Live action notifier reset")


if __name__ == '__main__':
    # Test the notifier
    import sys

    logging.basicConfig(level=logging.INFO)

    root = tk.Tk()
    root.withdraw()  # Hide main window

    notifier = LiveActionNotifier(
        my_name="Alex",
        name_variations=["Alex", "Al"],
        notification_duration=5,
        auto_approve=True
    )

    # Test transcript chunks
    test_chunks = [
        ("Manager", "Alex, can you follow up with the vendor about those training dates?"),
        ("Colleague", "Have Alex review the materials before the call tomorrow."),
        ("Manager", "Could Alex send that email to the team?"),
    ]

    print("Testing live action notifier...")
    print("Will show 3 test notifications...")

    for speaker, text in test_chunks:
        print(f"\nProcessing: {speaker}: {text}")
        notifier.process_transcript_chunk(text, speaker)
        time.sleep(2)

    # Wait for notifications
    time.sleep(15)

    # Show summary
    summary = notifier.get_summary()
    print(f"\n{'='*50}")
    print("SUMMARY:")
    print(f"  Detected: {summary['total_detected']}")
    print(f"  Confirmed: {summary['confirmed']}")
    print(f"  Ignored: {summary['ignored']}")
    print(f"{'='*50}")
