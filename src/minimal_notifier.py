"""Minimal custom notifications - small, top-left, brief."""

import tkinter as tk
import threading
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MinimalNotifier:
    """Show small, brief notifications in top-left corner."""

    def __init__(self):
        """Initialize notifier."""
        self.current_notification: Optional[tk.Toplevel] = None
        self.notification_queue = []
        self.showing = False

    def notify(self, message: str, duration: int = 2):
        """
        Show a minimal notification.

        Args:
            message: Short message to display
            duration: Seconds to show (default 2)
        """
        self.notification_queue.append((message, duration))
        if not self.showing:
            threading.Thread(target=self._show_next, daemon=True).start()

    def _show_next(self):
        """Show next notification in queue."""
        if not self.notification_queue:
            self.showing = False
            return

        self.showing = True
        message, duration = self.notification_queue.pop(0)

        try:
            # Create notification window
            root = tk.Tk()
            root.withdraw()  # Hide main window

            notification = tk.Toplevel(root)
            notification.title("")
            notification.overrideredirect(True)
            notification.attributes('-topmost', True)

            try:
                notification.attributes('-alpha', 0.9)
            except:
                pass

            # Style
            bg_color = '#2C3E50'
            fg_color = '#ECF0F1'

            frame = tk.Frame(notification, bg=bg_color, padx=15, pady=10)
            frame.pack()

            label = tk.Label(
                frame,
                text=message,
                font=('Segoe UI', 9),
                bg=bg_color,
                fg=fg_color
            )
            label.pack()

            # Position top-left
            notification.update_idletasks()
            x = 20
            y = 20
            notification.geometry(f"+{x}+{y}")

            notification.deiconify()

            # Auto-close after duration
            def close():
                try:
                    notification.destroy()
                    root.destroy()
                except:
                    pass
                # Show next if any
                self._show_next()

            notification.after(duration * 1000, close)

            # Allow click to dismiss
            notification.bind('<Button-1>', lambda e: close())

            root.mainloop()

        except Exception as e:
            logger.error(f"Error showing notification: {e}")
            self.showing = False
            # Try next
            if self.notification_queue:
                self._show_next()
