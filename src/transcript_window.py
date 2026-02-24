"""Live transcript display window."""

import tkinter as tk
from tkinter import scrolledtext
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TranscriptWindow:
    """Floating window to display live streaming transcript."""

    def __init__(self):
        """Initialize transcript window."""
        self.window: Optional[tk.Toplevel] = None
        self.text_widget: Optional[scrolledtext.ScrolledText] = None
        self.running = False
        self.transcript_text = ""

        logger.info("TranscriptWindow initialized")

    def show(self, parent_window: tk.Tk):
        """
        Show the transcript window.

        Args:
            parent_window: Parent Tkinter window
        """
        if self.window:
            return

        try:
            self.window = tk.Toplevel(parent_window)
            self.window.title("Live Transcript - Pilot")
            self.window.geometry("500x300+50+50")

            try:
                self.window.attributes('-alpha', 0.92)
            except:
                pass

            # Header
            header = tk.Frame(self.window, bg='#2C3E50', height=40)
            header.pack(fill=tk.X)

            title_label = tk.Label(
                header,
                text="🎤 Live Transcript",
                bg='#2C3E50',
                fg='white',
                font=('Segoe UI', 12, 'bold'),
                pady=10
            )
            title_label.pack()

            # Scrolled text area
            self.text_widget = scrolledtext.ScrolledText(
                self.window,
                wrap=tk.WORD,
                font=('Segoe UI', 11),
                bg='#f5f5f5',
                fg='#333',
                padx=15,
                pady=15,
                relief=tk.FLAT
            )
            self.text_widget.pack(fill=tk.BOTH, expand=True)

            # Make read-only
            self.text_widget.config(state=tk.DISABLED)

            # Footer with status
            footer = tk.Frame(self.window, bg='#ecf0f1', height=30)
            footer.pack(fill=tk.X)

            status_label = tk.Label(
                footer,
                text="Listening...",
                bg='#ecf0f1',
                fg='#7f8c8d',
                font=('Segoe UI', 9),
                pady=5
            )
            status_label.pack()

            self.running = True
            logger.info("Transcript window shown")

        except Exception as e:
            logger.error(f"Error showing transcript window: {e}")

    def hide(self):
        """Hide and destroy the transcript window."""
        if not self.window:
            return

        try:
            self.window.destroy()
            self.window = None
            self.text_widget = None
            self.running = False
            self.transcript_text = ""
            logger.info("Transcript window hidden")
        except Exception as e:
            logger.error(f"Error hiding transcript window: {e}")

    def update_transcript(self, text: str, is_final: bool = True):
        """
        Update transcript text (thread-safe).

        Args:
            text: New transcript text to append
            is_final: Whether this is finalized text (True) or partial (False)
        """
        if not self.window or not self.text_widget:
            return

        try:
            def _update():
                try:
                    if is_final:
                        # Append finalized text
                        self.transcript_text += text + " "

                        # Update display
                        self.text_widget.config(state=tk.NORMAL)
                        self.text_widget.delete(1.0, tk.END)
                        self.text_widget.insert(tk.END, self.transcript_text)
                        self.text_widget.config(state=tk.DISABLED)

                        # Auto-scroll to bottom
                        self.text_widget.see(tk.END)
                    else:
                        # Show partial text in different color (preview)
                        self.text_widget.config(state=tk.NORMAL)
                        self.text_widget.delete(1.0, tk.END)
                        self.text_widget.insert(tk.END, self.transcript_text)

                        # Add partial text in gray
                        partial_start = self.text_widget.index(tk.END)
                        self.text_widget.insert(tk.END, text, "partial")
                        self.text_widget.tag_config("partial", foreground="#999")

                        self.text_widget.config(state=tk.DISABLED)
                        self.text_widget.see(tk.END)

                except Exception as e:
                    logger.error(f"Error updating transcript text: {e}")

            # Schedule update on main thread
            self.window.after(0, _update)

        except Exception as e:
            logger.error(f"Error scheduling transcript update: {e}")

    def clear(self):
        """Clear transcript text."""
        self.transcript_text = ""
        if self.text_widget:
            try:
                self.text_widget.config(state=tk.NORMAL)
                self.text_widget.delete(1.0, tk.END)
                self.text_widget.config(state=tk.DISABLED)
            except:
                pass
