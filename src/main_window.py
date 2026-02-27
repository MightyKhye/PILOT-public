"""Persistent main dashboard window for Pilot."""

import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from .meeting_manager import MeetingState
from .config import Config

# ── Color palette ────────────────────────────────────────────────────────────
BG      = "#1a1a2e"
CARD    = "#16213e"
ACCENT  = "#00b4d8"
FG      = "#e0e0e0"
FG_DIM  = "#7a8898"
BORDER  = "#0f3460"
HOVER   = "#1e3060"

DOT_IDLE = "#4caf50"   # green
DOT_REC  = "#f44336"   # red
DOT_PROC = "#ffb300"   # amber

BTN_START    = ACCENT
BTN_STOP     = "#c62828"
BTN_DISABLED = "#2a2a4a"
# ─────────────────────────────────────────────────────────────────────────────


class MainWindow:
    """
    Persistent dashboard window for Pilot.

    Designed to run on the main thread via self.run() → root.mainloop().
    All public update_* methods are thread-safe (use root.after).
    """

    def __init__(self, app):
        """
        Args:
            app: MeetingListenerApp instance from src/main.py
        """
        self.app = app
        self._state: MeetingState = MeetingState.IDLE
        self._recording_start: Optional[float] = None
        self._timer_running = False
        self._upload_in_progress = False
        self._query_placeholder_active = True

        self.root = tk.Tk()
        self.root.title("Pilot")
        self.root.geometry("540x760")
        self.root.minsize(460, 580)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Set Windows AppUserModelID so the taskbar groups the window correctly
        # and shows the Pilot icon rather than the generic Python icon.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Pilot.MeetingAssistant"
            )
        except Exception:
            pass

        # Set window icon — iconbitmap (ICO) for taskbar/Alt+Tab, iconphoto (PNG) for title bar
        try:
            icon_ico_path = Path(__file__).parent.parent / "assets" / "icon.ico"
            self.root.iconbitmap(str(icon_ico_path))
        except Exception:
            pass
        try:
            from PIL import Image, ImageTk
            icon_path = Path(__file__).parent.parent / "assets" / "icon.png"
            _img = Image.open(icon_path).convert("RGBA")
            self._icon_photo = ImageTk.PhotoImage(_img)
            self.root.iconphoto(True, self._icon_photo)
        except Exception:
            pass

        # Style ttk widgets
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Upload.Horizontal.TProgressbar",
            troughcolor=BORDER,
            background=ACCENT,
            bordercolor=CARD,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
        )

        self._build_ui()
        self._load_recent_meetings()

    # ── Build layout ─────────────────────────────────────────────────────────

    def _build_ui(self):
        """Construct all widgets in layout order."""

        # ── Header ───────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=CARD, pady=14, padx=20)
        header.pack(fill=tk.X)

        tk.Label(
            header, text="PILOT",
            bg=CARD, fg=ACCENT, font=("Segoe UI", 20, "bold")
        ).pack(side=tk.LEFT)

        right = tk.Frame(header, bg=CARD)
        right.pack(side=tk.RIGHT, pady=2)

        self._dot_canvas = tk.Canvas(
            right, width=14, height=14, bg=CARD, highlightthickness=0
        )
        self._dot_canvas.pack(side=tk.LEFT, padx=(0, 8))
        self._dot = self._dot_canvas.create_oval(2, 2, 12, 12, fill=DOT_IDLE, outline="")

        self._status_label = tk.Label(
            right, text="Ready to record",
            bg=CARD, fg=FG, font=("Segoe UI", 10)
        )
        self._status_label.pack(side=tk.LEFT)

        # ── Separator ────────────────────────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

        # ── Primary record button ─────────────────────────────────────────────
        self._btn_outer = tk.Frame(self.root, bg=BG, pady=20, padx=28)
        self._btn_outer.pack(fill=tk.X)

        self._record_btn = tk.Button(
            self._btn_outer,
            text="Start Recording",
            command=self._toggle_recording,
            bg=BTN_START, fg="white",
            font=("Segoe UI", 13, "bold"),
            relief=tk.FLAT, cursor="hand2",
            padx=32, pady=14,
            activebackground="#0096b3", activeforeground="white",
        )
        self._record_btn.pack(fill=tk.X)

        # ── Live feed panel (hidden when idle) ────────────────────────────────
        # Created here but not packed; inserted after _btn_outer when needed.
        self._live_frame = tk.Frame(self.root, bg=CARD, pady=12, padx=20)

        tk.Label(
            self._live_frame, text="LIVE FEED",
            bg=CARD, fg=ACCENT, font=("Segoe UI", 8, "bold")
        ).pack(anchor="w")

        stats_row = tk.Frame(self._live_frame, bg=CARD)
        stats_row.pack(fill=tk.X, pady=(6, 2))

        self._chunks_label = tk.Label(
            stats_row, text="Chunks: 0",
            bg=CARD, fg=FG, font=("Segoe UI", 9)
        )
        self._chunks_label.pack(side=tk.LEFT, padx=(0, 24))

        self._elapsed_label = tk.Label(
            stats_row, text="Elapsed: 0:00",
            bg=CARD, fg=FG, font=("Segoe UI", 9)
        )
        self._elapsed_label.pack(side=tk.LEFT)

        self._latest_action_label = tk.Label(
            self._live_frame, text="Last action: —",
            bg=CARD, fg=FG_DIM, font=("Segoe UI", 9),
            wraplength=460, justify="left"
        )
        self._latest_action_label.pack(anchor="w", pady=(2, 0))

        # ── Upload section ────────────────────────────────────────────────────
        upload_outer = tk.Frame(self.root, bg=BG, padx=28, pady=4)
        upload_outer.pack(fill=tk.X)

        upload_card = tk.Frame(upload_outer, bg=CARD, pady=14, padx=16)
        upload_card.pack(fill=tk.X)

        upload_top = tk.Frame(upload_card, bg=CARD)
        upload_top.pack(fill=tk.X)

        tk.Label(
            upload_top, text="Upload Recording(s)",
            bg=CARD, fg=FG, font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT)

        self._upload_btn = tk.Button(
            upload_top, text="Browse",
            command=self._start_upload,
            bg=BORDER, fg=FG,
            font=("Segoe UI", 9), relief=tk.FLAT,
            cursor="hand2", padx=12, pady=4,
            activebackground=HOVER,
        )
        self._upload_btn.pack(side=tk.RIGHT)

        self._upload_file_label = tk.Label(
            upload_card, text="",
            bg=CARD, fg=FG_DIM, font=("Segoe UI", 8)
        )
        self._upload_file_label.pack(anchor="w", pady=(4, 2))

        # Progress bar + status — packed only during an active upload
        self._upload_progress = ttk.Progressbar(
            upload_card,
            style="Upload.Horizontal.TProgressbar",
            mode="determinate",
        )
        self._upload_status_label = tk.Label(
            upload_card, text="",
            bg=CARD, fg=FG_DIM, font=("Segoe UI", 8)
        )

        # ── Separator ────────────────────────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

        # ── Recent meetings ───────────────────────────────────────────────────
        meetings_outer = tk.Frame(self.root, bg=BG, padx=28, pady=8)
        meetings_outer.pack(fill=tk.X)

        header_row = tk.Frame(meetings_outer, bg=BG)
        header_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            header_row, text="Recent Meetings",
            bg=BG, fg=FG, font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT)

        self._refresh_btn = tk.Button(
            header_row, text="Refresh",
            command=self._load_recent_meetings,
            bg=BG, fg=FG_DIM,
            font=("Segoe UI", 8), relief=tk.FLAT,
            cursor="hand2", padx=6, pady=2,
            activebackground=HOVER,
        )
        self._refresh_btn.pack(side=tk.RIGHT)

        self._meetings_frame = tk.Frame(meetings_outer, bg=CARD)
        self._meetings_frame.pack(fill=tk.X)

        # ── Separator ────────────────────────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

        # ── Bottom bar: Ask + Status Report ───────────────────────────────────
        # CARD background gives a subtle visual distinction from the BG content above
        bottom_outer = tk.Frame(self.root, bg=CARD, padx=28, pady=12)
        bottom_outer.pack(fill=tk.BOTH, expand=True)

        # Two equal columns
        bottom_left = tk.Frame(bottom_outer, bg=CARD)
        bottom_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 16))

        bottom_right = tk.Frame(bottom_outer, bg=CARD)
        bottom_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0))

        # ── LEFT: Ask about meetings ──────────────────────────────────────────
        query_outer = bottom_left

        tk.Label(
            query_outer, text="Ask about meetings",
            bg=CARD, fg=FG, font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(0, 5))

        input_row = tk.Frame(query_outer, bg=CARD)
        input_row.pack(fill=tk.X)

        # Wrapper frame gives the entry a clean 1px border without tkinter's box relief
        entry_wrapper = tk.Frame(input_row, bg=BORDER, padx=1, pady=1)
        entry_wrapper.pack(side=tk.LEFT, fill=tk.X, expand=True)

        PLACEHOLDER = "What action items are assigned to me?"
        self._query_entry = tk.Entry(
            entry_wrapper,
            bg=BG, fg=FG_DIM, insertbackground=FG,
            font=("Segoe UI", 9), relief=tk.FLAT,
            highlightthickness=0,
        )
        self._query_entry.pack(fill=tk.X, ipady=5)
        self._query_entry.insert(0, PLACEHOLDER)

        def _focus_in(e):
            if self._query_placeholder_active:
                self._query_entry.delete(0, tk.END)
                self._query_entry.config(fg=FG)
                self._query_placeholder_active = False

        def _focus_out(e):
            if not self._query_entry.get().strip():
                self._query_entry.insert(0, PLACEHOLDER)
                self._query_entry.config(fg=FG_DIM)
                self._query_placeholder_active = True

        self._query_entry.bind("<FocusIn>", _focus_in)
        self._query_entry.bind("<FocusOut>", _focus_out)
        self._query_entry.bind("<Return>", lambda e: self._submit_query())

        self._ask_btn = tk.Button(
            input_row, text="Ask",
            command=self._submit_query,
            bg=ACCENT, fg="white",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT,
            cursor="hand2", padx=14, pady=5,
            activebackground="#0096b3",
        )
        self._ask_btn.pack(side=tk.LEFT, padx=(6, 0))

        # Answer area — packed on first query
        self._answer_frame = tk.Frame(query_outer, bg=CARD)
        self._answer_text = scrolledtext.ScrolledText(
            self._answer_frame,
            bg=BG, fg=FG,
            font=("Segoe UI", 9),
            relief=tk.FLAT, wrap=tk.WORD,
            height=7, padx=10, pady=8,
            insertbackground=FG,
        )
        self._answer_text.pack(fill=tk.BOTH, expand=True)
        self._answer_text.config(state=tk.DISABLED)

        # ── RIGHT: Status Report ──────────────────────────────────────────────
        tk.Label(
            bottom_right, text="Status Report",
            bg=CARD, fg=FG, font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(0, 5))

        self._status_report_btn = tk.Button(
            bottom_right, text="Generate Status Report",
            command=self._run_status_report,
            bg=ACCENT, fg="white",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT,
            cursor="hand2", padx=14, pady=5,
            activebackground="#0096b3",
        )
        self._status_report_btn.pack(fill=tk.X)

        self._status_report_status = tk.Label(
            bottom_right, text="", bg=CARD, fg=FG_DIM, font=("Segoe UI", 8)
        )
        self._status_report_status.pack(anchor="w", pady=(5, 0))

    # ── Window lifecycle ─────────────────────────────────────────────────────

    def run(self):
        """Block on the tkinter event loop. Call from the main thread."""
        self.root.mainloop()

    def destroy(self):
        """Cleanly stop the mainloop and destroy the window."""
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def show(self):
        """Bring the window to the foreground."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_close(self):
        """Hide to tray on window close rather than quitting."""
        self.root.withdraw()

    # ── State updates (thread-safe) ───────────────────────────────────────────

    def update_state(self, state: MeetingState, chunk_count: int = 0):
        """Thread-safe: schedule a UI state update on the main thread."""
        self.root.after(0, self._apply_state, state, chunk_count)

    def _apply_state(self, state: MeetingState, chunk_count: int = 0):
        """Apply state to all relevant widgets. Must run on main thread."""
        self._state = state

        if state == MeetingState.IDLE:
            self._dot_canvas.itemconfig(self._dot, fill=DOT_IDLE)
            self._status_label.config(text="Ready to record")
            self._record_btn.config(
                text="Start Recording", bg=BTN_START,
                state=tk.NORMAL, cursor="hand2",
                activebackground="#0096b3",
            )
            self._hide_live_feed()
            self._stop_timer()
            self._recording_start = None
            self._load_recent_meetings()  # Refresh after a meeting ends

        elif state == MeetingState.RECORDING:
            self._dot_canvas.itemconfig(self._dot, fill=DOT_REC)
            self._record_btn.config(
                text="Stop Recording", bg=BTN_STOP,
                state=tk.NORMAL, cursor="hand2",
                activebackground="#b71c1c",
            )
            if self._recording_start is None:
                self._recording_start = time.monotonic()
            self._show_live_feed()
            self._start_timer()
            self._chunks_label.config(text=f"Chunks: {chunk_count}")

        elif state == MeetingState.PROCESSING:
            self._dot_canvas.itemconfig(self._dot, fill=DOT_PROC)
            self._status_label.config(text="Processing…")
            self._record_btn.config(
                text="Processing…", bg=BTN_DISABLED,
                state=tk.DISABLED, cursor="",
            )
            self._stop_timer()
            self._show_live_feed()
            self._chunks_label.config(text=f"Chunks: {chunk_count}")

        elif state == MeetingState.ERROR:
            self._dot_canvas.itemconfig(self._dot, fill="#888888")
            self._status_label.config(text="Error — see logs")
            self._record_btn.config(
                text="Start Recording", bg=BTN_START,
                state=tk.NORMAL, cursor="hand2",
                activebackground="#0096b3",
            )
            self._hide_live_feed()
            self._stop_timer()

    # ── Live feed ─────────────────────────────────────────────────────────────

    def _show_live_feed(self):
        if not self._live_frame.winfo_manager():
            self._live_frame.pack(
                fill=tk.X, padx=28, pady=(0, 4),
                after=self._btn_outer,
            )

    def _hide_live_feed(self):
        self._live_frame.pack_forget()

    def update_live_feed(self, chunk_count: int, latest_action: str = ""):
        """Thread-safe live feed update."""
        self.root.after(0, self._apply_live_feed, chunk_count, latest_action)

    def _apply_live_feed(self, chunk_count: int, latest_action: str):
        self._chunks_label.config(text=f"Chunks: {chunk_count}")
        if latest_action:
            snippet = (latest_action[:100] + "…") if len(latest_action) > 100 else latest_action
            self._latest_action_label.config(text=f"Last action: {snippet}")

    # ── Recording timer ────────────────────────────────────────────────────────

    def _start_timer(self):
        if not self._timer_running:
            self._timer_running = True
            self._tick()

    def _stop_timer(self):
        self._timer_running = False

    def _tick(self):
        if not self._timer_running:
            return
        if self._recording_start is not None:
            elapsed = int(time.monotonic() - self._recording_start)
            m, s = divmod(elapsed, 60)
            self._elapsed_label.config(text=f"Elapsed: {m}:{s:02d}")
            self._status_label.config(text=f"Recording — {m}:{s:02d}")
        self.root.after(1000, self._tick)

    # ── Recording button ──────────────────────────────────────────────────────

    def _toggle_recording(self):
        if self._state == MeetingState.IDLE:
            threading.Thread(
                target=self.app.start_recording, daemon=True
            ).start()
        elif self._state == MeetingState.RECORDING:
            threading.Thread(
                target=self.app.stop_recording, daemon=True
            ).start()

    # ── Upload ────────────────────────────────────────────────────────────────

    def trigger_upload(self):
        """Show the window and start the file picker. Callable from tray."""
        self.show()
        self.root.after(100, self._start_upload)

    def _start_upload(self):
        if self._upload_in_progress:
            return

        file_paths = filedialog.askopenfilenames(
            title="Select Meeting Recording(s)",
            parent=self.root,
            filetypes=[
                ("Audio Files", "*.wav *.m4a *.mp3 *.mp4 *.aac *.flac *.ogg"),
                ("All Files", "*.*"),
            ],
        )
        if not file_paths:
            return

        audio_files = [Path(p) for p in file_paths]
        total_files = len(audio_files)

        if total_files == 1:
            self._upload_file_label.config(text=audio_files[0].name)
        else:
            self._upload_file_label.config(text=f"{total_files} files selected")

        self._upload_in_progress = True
        self._upload_btn.config(state=tk.DISABLED, cursor="")

        # Show inline progress widgets
        self._upload_progress.pack(fill=tk.X, pady=(4, 2))
        self._upload_status_label.pack(anchor="w")
        self._upload_progress["value"] = 0
        self._upload_status_label.config(text="Starting…")

        def _run():
            succeeded = 0
            failed = 0

            # Creep animation: slowly inches the progress bar toward the next milestone
            # while a chunk is being processed (each chunk can take 30+ seconds).
            # Uses a mutable list as a cancellation flag so nested closures can share it.
            _creep_cancel = [False]

            def _cancel_creep():
                _creep_cancel[0] = True

            def _start_creep(target_pct: float):
                """Advance the bar toward target_pct - 0.5 at 0.2% per 300ms."""
                _creep_cancel[0] = False
                ceiling = target_pct - 0.5

                def _step():
                    if _creep_cancel[0]:
                        return
                    cur = self._upload_progress["value"]
                    if cur < ceiling:
                        self._upload_progress["value"] = min(cur + 0.2, ceiling)
                        self.root.after(300, _step)

                self.root.after(300, _step)

            for i, audio_file in enumerate(audio_files, 1):
                # Update file indicator for each file
                def _set_file(n=i, name=audio_file.name):
                    if total_files > 1:
                        self._upload_file_label.config(
                            text=f"File {n} of {total_files}: {name}"
                        )
                    self._upload_progress["value"] = 0
                    self._upload_status_label.config(text="Starting…")
                self.root.after(0, _set_file)

                try:
                    def _cb(step: str, done: int = 0, total: int = 0):
                        def _update():
                            _cancel_creep()
                            self._upload_status_label.config(text=step)
                            if total:
                                new_val = (done / total) * 100
                                self._upload_progress["value"] = new_val
                                # Creep toward next chunk's milestone while it processes
                                if done < total:
                                    _start_creep((done + 1) / total * 100)
                            else:
                                cur = self._upload_progress["value"]
                                self._upload_progress["value"] = min(cur + 1.5, 95)
                        self.root.after(0, _update)

                    html_path = self.app.manager.process_uploaded_file(
                        audio_path=audio_file,
                        status_callback=_cb,
                    )

                    if html_path:
                        succeeded += 1
                        # Auto-open browser only for single-file uploads
                        if total_files == 1:
                            try:
                                if sys.platform == "win32":
                                    os.startfile(str(html_path))
                            except Exception:
                                pass
                    else:
                        failed += 1
                        logger.error(f"process_uploaded_file returned None for {audio_file.name}")

                except Exception as exc:
                    failed += 1
                    logger.error(f"Error processing {audio_file.name}: {exc}", exc_info=True)
                    def _show_err(name=audio_file.name, e=exc):
                        self._upload_status_label.config(
                            text=f"Error on {name}: {str(e)[:60]} — continuing…"
                        )
                    self.root.after(0, _show_err)

            # All files done
            def _finish(s=succeeded, f=failed):
                self._upload_in_progress = False
                self._upload_btn.config(state=tk.NORMAL, cursor="hand2")
                self._load_recent_meetings()
                if total_files == 1:
                    if s:
                        self._upload_progress["value"] = 100
                        self._upload_status_label.config(text="Complete — opening in browser")
                    else:
                        self._upload_progress["value"] = 0
                        self._upload_status_label.config(text="Processing failed — check logs")
                else:
                    self._upload_progress["value"] = 100 if f == 0 else 0
                    if f == 0:
                        self._upload_status_label.config(text=f"All {total_files} files complete")
                    else:
                        self._upload_status_label.config(
                            text=f"{s} of {total_files} succeeded, {f} failed — check logs"
                        )
                self.root.after(4000, self._reset_upload_ui)

            self.root.after(0, _finish)

        threading.Thread(target=_run, daemon=True).start()

    def _reset_upload_ui(self):
        self._upload_progress.pack_forget()
        self._upload_status_label.pack_forget()
        self._upload_file_label.config(text="")
        self._upload_progress["value"] = 0
        self._upload_status_label.config(text="")

    # ── Recent meetings ───────────────────────────────────────────────────────

    def _load_recent_meetings(self):
        """Rebuild the recent meetings list from persistent memory."""
        for w in self._meetings_frame.winfo_children():
            w.destroy()

        meetings = self.app.manager.memory.memory_data.get("meetings", [])
        recent = list(reversed(meetings))[:5]

        if not recent:
            tk.Label(
                self._meetings_frame,
                text="No meetings recorded yet.",
                bg=CARD, fg=FG_DIM, font=("Segoe UI", 9), pady=10,
            ).pack()
            return

        for meeting in recent:
            self._add_meeting_row(meeting)

    @staticmethod
    def _format_duration(raw) -> str:
        """
        Normalize the stored duration string to a clean display format.

        The meeting manager stores duration as a pre-formatted string, e.g.:
          '23m'      → '23 min'
          '58m'      → '58 min'
          '1h 42m'   → '1h 42m'   (already good, keep as-is)
          '0m'       → '< 1 min'  (zero usually means the recording was cut short)
          None / ''  → '—'
        """
        if not raw:
            return "—"
        raw = str(raw).strip()
        if not raw or raw == "?":
            return "—"

        # Already contains hours component — leave formatting as-is
        if "h" in raw:
            return raw

        # Pure minutes: e.g. '23m'
        try:
            mins = int(raw.rstrip("m"))
        except ValueError:
            return raw  # Unknown format — pass through

        if mins == 0:
            return "< 1 min"
        return f"{mins} min"

    def _add_meeting_row(self, meeting: dict):
        meeting_id = meeting.get("meeting_id", "")
        date_str   = meeting.get("date", "")
        duration   = self._format_duration(meeting.get("duration"))
        summary    = meeting.get("summary", "")

        # Format date
        try:
            dt = datetime.fromisoformat(date_str)
            display_date = dt.strftime("%b %d, %Y  %I:%M %p")
        except Exception:
            display_date = date_str[:16] if date_str else "Unknown"

        # First substantive line of summary as snippet
        snippet = ""
        for line in summary.splitlines():
            line = line.strip()
            if line and not line.startswith(("=", "#", "-")):
                snippet = (line[:84] + "…") if len(line) > 84 else line
                break
        if not snippet:
            snippet = "No summary available"

        html_path = self._find_meeting_html(meeting_id)

        row = tk.Frame(self._meetings_frame, bg=CARD, cursor="hand2")
        row.pack(fill=tk.X, pady=1)

        meta = tk.Label(
            row,
            text=f"{display_date}   ·   {duration}",
            bg=CARD, fg=ACCENT, font=("Segoe UI", 8, "bold"),
            padx=10, pady=5,
        )
        meta.pack(anchor="w")

        snip = tk.Label(
            row,
            text=snippet,
            bg=CARD, fg=FG_DIM, font=("Segoe UI", 8),
            padx=10, wraplength=450, justify="left",
        )
        snip.pack(anchor="w", pady=(0, 6))

        # Hover + click on row and all children
        def _enter(e, widgets=(row, meta, snip)):
            for w in widgets:
                w.config(bg=HOVER)

        def _leave(e, widgets=(row, meta, snip)):
            for w in widgets:
                w.config(bg=CARD)

        def _click(e=None, path=html_path):
            if path and path.exists():
                try:
                    os.startfile(str(path))
                except Exception:
                    pass

        for w in (row, meta, snip):
            w.bind("<Enter>", _enter)
            w.bind("<Leave>", _leave)
            w.bind("<Button-1>", _click)

    def _find_meeting_html(self, meeting_id: str) -> Optional[Path]:
        if not meeting_id:
            return None
        for search_dir in (Config.SUMMARIES_DIR, Config.MEETINGS_DIR):
            if not search_dir.exists():
                continue
            matches = list(search_dir.glob(f"*{meeting_id}*.html"))
            if matches:
                return matches[0]
        return None

    # ── Query bar ─────────────────────────────────────────────────────────────

    def focus_query(self):
        """Bring window to front and focus the query input."""
        self.show()
        self._query_entry.focus_set()

    def _submit_query(self):
        if self._query_placeholder_active:
            return
        question = self._query_entry.get().strip()
        if not question:
            return

        self._ask_btn.config(state=tk.DISABLED, cursor="")
        self._show_answer("Searching your meeting history…")

        def _run():
            try:
                meetings = self.app.manager.memory.memory_data.get("meetings", [])
                if not meetings:
                    self.root.after(0, self._show_answer, "No meetings recorded yet.")
                    return

                result = self.app.manager.analyzer.query_meetings(question, meetings)
                answer     = result.get("answer", "No answer returned.")
                confidence = result.get("confidence", "")
                sources    = result.get("sources", [])

                lines = [answer]
                if confidence:
                    lines.append(f"\nConfidence: {confidence}")
                if sources:
                    lines.append(f"  ·  {len(sources)} meeting(s) referenced")

                self.root.after(0, self._show_answer, "".join(lines))

            except Exception as exc:
                self.root.after(0, self._show_answer, f"Error: {exc}")
            finally:
                self.root.after(
                    0, lambda: self._ask_btn.config(state=tk.NORMAL, cursor="hand2")
                )

        threading.Thread(target=_run, daemon=True).start()

    # ── Status Report ─────────────────────────────────────────────────────────

    def _run_status_report(self):
        """Generate a PM-focused status report and hand off to run_status_check()."""
        self._status_report_btn.config(state=tk.DISABLED, cursor="")
        self._status_report_status.config(text="Generating…")

        def _run():
            try:
                self.app.run_status_check()
                self.root.after(
                    0, lambda: self._status_report_status.config(text="Done — report opened")
                )
            except Exception as exc:
                self.root.after(
                    0, lambda: self._status_report_status.config(
                        text=f"Error: {str(exc)[:60]}"
                    )
                )
            finally:
                self.root.after(
                    0, lambda: self._status_report_btn.config(
                        state=tk.NORMAL, cursor="hand2"
                    )
                )

        threading.Thread(target=_run, daemon=True).start()

    def _show_answer(self, text: str):
        """Display answer text and show the answer panel if not yet visible."""
        if not self._answer_frame.winfo_manager():
            self._answer_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self._answer_text.config(state=tk.NORMAL)
        self._answer_text.delete("1.0", tk.END)
        self._answer_text.insert(tk.END, text)
        self._answer_text.config(state=tk.DISABLED)
