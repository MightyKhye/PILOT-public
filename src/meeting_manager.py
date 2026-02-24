"""Meeting manager to orchestrate audio capture, transcription, and analysis."""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable
from enum import Enum

from .audio_capture import AudioCapture
from .transcription import Transcriber
from .ai_analyzer import MeetingAnalyzer
from .notifier import MeetingNotifier
from .config import Config
from .persistent_memory import PersistentMemory
from .audio_snippet_extractor import AudioSnippetExtractor
from .html_summary_generator import HTMLSummaryGenerator
from .live_action_notifier import LiveActionNotifier

# Optional: streaming transcription (fail-safe if not available)
try:
    from .streaming_transcriber import StreamingTranscriber
    STREAMING_AVAILABLE = True
except ImportError:
    STREAMING_AVAILABLE = False
    logger.warning("Streaming transcription not available")

logger = logging.getLogger(__name__)


class MeetingState(Enum):
    """Meeting recording states."""
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    ERROR = "error"


class MeetingManager:
    """Orchestrates meeting recording, transcription, and analysis."""

    def __init__(self):
        """Initialize meeting manager."""
        # Initialize components
        self.audio_capture = AudioCapture()
        self.transcriber = Transcriber()
        self.analyzer = MeetingAnalyzer()
        # Notifier disabled - using only minimal notifier in main.py
        # self.notifier = MeetingNotifier()
        self.notifier = None
        self.memory = PersistentMemory()

        # Initialize snippet extractor if enabled
        if Config.SNIPPET_ENABLED:
            self.snippet_extractor = AudioSnippetExtractor(
                recordings_dir=Config.RECORDINGS_DIR,
                snippets_dir=Config.SNIPPETS_DIR
            )
        else:
            self.snippet_extractor = None

        # Initialize HTML summary generator
        self.html_generator = HTMLSummaryGenerator()

        # Initialize streaming transcriber if available (fail-safe)
        self.streaming_transcriber = None
        if STREAMING_AVAILABLE:
            try:
                self.streaming_transcriber = StreamingTranscriber(
                    on_transcript=self._on_streaming_transcript
                )
                logger.info("Streaming transcription initialized")
            except Exception as e:
                logger.warning(f"Could not initialize streaming transcription: {e}")
                self.streaming_transcriber = None

        # Initialize live action notifier
        try:
            self.live_action_notifier = LiveActionNotifier(
                my_name=Config.MY_NAME,
                name_variations=Config.MY_NAME_VARIATIONS,
                notification_duration=Config.NOTIFICATION_DURATION,
                auto_approve=(Config.AUTO_APPROVE_TIMEOUT > 0),
                enabled=Config.LIVE_ACTION_NOTIFICATIONS
            )
            logger.info(f"Live action notifier initialized for: {Config.MY_NAME}")
        except Exception as e:
            logger.warning(f"Could not initialize live action notifier: {e}")
            self.live_action_notifier = None

        # State management - THREAD SAFE
        self.state = MeetingState.IDLE
        self.meeting_id: Optional[str] = None
        self.meeting_start_time: Optional[datetime] = None
        # RACE CONDITION FIX: Use lock for all state changes, single source of truth
        self._state_lock = threading.Lock()  # Protects state changes
        self._stop_event = threading.Event()  # Signals threads to stop
        self._stopping = False  # True only while stop_meeting() is actively running

        # Worker threads
        self.processing_thread: Optional[threading.Thread] = None
        self.running = False  # Deprecated - use _stop_event instead

        # Meeting data - MEMORY OPTIMIZED
        # Stream to disk to prevent memory leaks during long meetings
        self.transcriptions = []  # Keep only last 10 chunks in memory
        self.analyses = []  # Keep only last 10 chunks in memory
        self.transcription_count = 0  # Total count for disk file naming
        self.analysis_count = 0  # Total count for disk file naming
        self.action_item_snippets = {}  # Maps action item hash to snippet path
        self.action_items_with_snippets = []  # List of (action_item_text, snippet_path) tuples
        # Memory management settings
        self.max_chunks_in_memory = 10  # Keep only last 10 chunks
        self.chunks_between_disk_flush = 5  # Write to disk every 5 chunks

        # Connection management
        self.is_online = True
        self.failed_chunks = []  # Queue of chunks that failed due to connection issues
        self.last_connection_notification = None  # Track when we last notified about connection

        # Silence detection
        self.last_audio_activity = None  # Track last time audio was received
        self.silence_timeout = 180  # Stop after 180 seconds (3 minutes) of silence
        self.silence_monitor_thread: Optional[threading.Thread] = None

        # Callbacks
        self.state_change_callback: Optional[Callable] = None

        # Ensure directories exist
        Config.create_directories()

    def start_meeting(self, callback: Optional[Callable] = None) -> bool:
        """
        Start recording and processing a meeting.

        Args:
            callback: Optional callback for state changes

        Returns:
            True if started successfully
        """
        if self.state != MeetingState.IDLE:
            logger.warning(f"Cannot start meeting in state: {self.state}")
            return False

        try:
            # Reset from previous meeting
            self._reset()

            # Load context from persistent memory
            historical_context = self.memory.get_context_summary()
            if historical_context:
                logger.info("Loaded historical context from previous meetings")

            # Generate meeting ID
            self.meeting_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.meeting_start_time = datetime.now()
            self.state_change_callback = callback

            logger.info(f"Starting meeting: {self.meeting_id}")

            # Reset live action notifier for new meeting
            if self.live_action_notifier:
                self.live_action_notifier.reset()
                logger.info("Live action notifier reset for new meeting")

            # Start notifier (disabled - using minimal notifier in main.py)
            # if self.notifier:
            #     self.notifier.start()
            #     self.notifier.notify_status("Recording started")

            # RACE CONDITION FIX: Start streaming BEFORE audio capture
            # This ensures websocket is ready when audio frames start arriving
            if self.streaming_transcriber:
                try:
                    import time
                    # Use 48000 Hz to match microphone (AMD Audio Device uses 48kHz)
                    # AssemblyAI supports 8000, 16000, 22050, 44100, 48000 Hz
                    logger.info("Starting streaming transcription (before audio capture)...")
                    self.streaming_transcriber.start_streaming(sample_rate=48000)

                    # Wait for websocket to fully connect (usually takes ~400ms)
                    # Check is_streaming flag with timeout
                    for i in range(10):  # Max 1 second wait
                        if self.streaming_transcriber.is_streaming:
                            logger.info(f"Streaming ready after {i*100}ms")
                            break
                        time.sleep(0.1)

                    if not self.streaming_transcriber.is_streaming:
                        logger.warning("Streaming did not become ready within 1 second")
                    else:
                        logger.info("Streaming transcription ready at 48000Hz")
                except Exception as e:
                    logger.warning(f"Could not start streaming transcription: {e}")
                    # Continue without streaming - chunk-based system still works

            # Start audio capture (use microphone to capture ambient audio)
            # Force use of actual microphone device, not default mapper
            # Pass audio frame callback for streaming transcription if available
            audio_frame_callback = None
            if self.streaming_transcriber:
                audio_frame_callback = self._on_audio_frame

            self.audio_capture.start_recording(
                use_microphone=True,
                microphone_device_index=Config.MICROPHONE_DEVICE_INDEX,  # Use config (auto-detect if None)
                audio_frame_callback=audio_frame_callback
            )

            # Start processing thread (daemon=False for clean shutdown)
            # RACE CONDITION FIX: Clear stop event for new meeting
            self._stop_event.clear()
            self.processing_thread = threading.Thread(
                target=self._processing_loop,
                daemon=False,  # Changed: Allow proper cleanup before exit
                name="MeetingProcessing"
            )
            self.processing_thread.start()

            # Start silence monitor thread (daemon=False for clean shutdown)
            self.last_audio_activity = datetime.now()  # Initialize
            self.silence_monitor_thread = threading.Thread(
                target=self._silence_monitor_loop,
                daemon=False,  # Changed: Allow proper cleanup before exit
                name="SilenceMonitor"
            )
            self.silence_monitor_thread.start()

            # Update state
            self._update_state(MeetingState.RECORDING)

            logger.info("Meeting recording started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start meeting: {e}")
            self._update_state(MeetingState.ERROR)
            # if self.notifier:
            #     self.notifier.notify_error(f"Failed to start recording: {str(e)}")
            return False

    def stop_meeting(self) -> Optional[str]:
        """
        Stop recording and generate meeting summary.

        Returns:
            Path to meeting summary file or None if failed
        """
        # Thread-safe guard: prevent duplicate stop calls and no-op if already idle
        with self._state_lock:
            if self.state == MeetingState.IDLE:
                logger.warning("No meeting in progress")
                return None

            # _stopping flag distinguishes "stop in progress" from "chunk being transcribed"
            # (both previously mapped to PROCESSING state, causing early bail-out on click-during-chunk)
            if self._stopping:
                logger.warning("Stop already in progress")
                return None

            self._stopping = True
            logger.info(f"[STOP] _stopping=True, state={self.state.value}")

        try:
            logger.info("Stopping meeting...")

            # Update state to processing so UI shows we're wrapping up
            self._update_state(MeetingState.PROCESSING)

            # Stop streaming transcription if running (fail-safe)
            if self.streaming_transcriber:
                try:
                    self.streaming_transcriber.stop_streaming()
                    logger.info("Streaming transcription stopped")
                except Exception as e:
                    logger.warning(f"Error stopping streaming transcription: {e}")

            # Stop audio capture
            self.audio_capture.stop_recording()

            # Stop processing thread - RACE CONDITION FIX: Use event instead of flag
            self._stop_event.set()  # Signal threads to stop (also halts _on_audio_frame buffering)
            if self.processing_thread and self.processing_thread.is_alive():
                logger.info("Waiting for processing thread to finish current transcription...")
                # 45s timeout: AssemblyAI batch transcription typically takes 20-30s.
                # The previous 8s timeout caused the thread to be abandoned mid-call,
                # leaving whole 30-second chunks untranscribed.
                self.processing_thread.join(timeout=45)

                if self.processing_thread.is_alive():
                    logger.warning("Processing thread still running after 45s — proceeding with transcriptions collected so far")
                else:
                    logger.info("Processing thread completed successfully")

            # Always process remaining chunks, including the final partial chunk
            # saved by audio_capture.stop_recording() just before this point.
            # Previously this was skipped when the processing thread timed out,
            # causing the last 27-second chunk to be silently dropped.
            # _process_remaining_chunks() has its own 15s budget so this is bounded.
            logger.info(f"Processing remaining chunks in queue ({len(self.transcriptions)} transcriptions so far)")
            self._process_remaining_chunks()

            # Generate summary
            summary_path = self._generate_meeting_summary()

            # Save to persistent memory
            if summary_path:
                self._save_to_memory()

            # Notify user (disabled - using minimal notifier in main.py)
            # if summary_path and self.notifier:
            #     duration = self._get_meeting_duration()
            #     self.notifier.notify_summary(
            #         "Meeting summary has been generated and saved.",
            #         duration
            #     )
            #     # Stop notifier (after a delay for last notifications)
            #     time.sleep(3)
            #     self.notifier.stop()

            # Don't reset here - keep data available for review
            # Reset will happen when starting next meeting
            self._update_state(MeetingState.IDLE)

            logger.info("Meeting stopped successfully")
            return summary_path

        except Exception as e:
            logger.error(f"Error stopping meeting: {e}")
            self._update_state(MeetingState.ERROR)
            return None

        finally:
            self._stopping = False

    def _silence_monitor_loop(self):
        """Monitor for prolonged silence and auto-stop recording. THREAD SAFE."""
        logger.info(f"[THREAD: {threading.current_thread().name}] Silence monitor started")

        # RACE CONDITION FIX: Use stop event instead of self.running
        while not self._stop_event.is_set() and not self._is_state(MeetingState.IDLE):
            try:
                # Use event wait with timeout instead of sleep for immediate stop response
                if self._stop_event.wait(timeout=10):  # Check every 10 seconds
                    break  # Stop event was set

                if not self.last_audio_activity:
                    continue

                # Check if silence timeout exceeded
                elapsed = (datetime.now() - self.last_audio_activity).total_seconds()
                if elapsed >= self.silence_timeout:
                    logger.info(f"Silence detected for {elapsed:.0f}s - auto-stopping recording")
                    # Stop recording due to silence
                    threading.Thread(target=self.stop_meeting, daemon=True, name="AutoStop").start()
                    break

            except Exception as e:
                logger.error(f"Error in silence monitor: {e}")
                time.sleep(1)

        logger.info(f"[THREAD: {threading.current_thread().name}] Silence monitor ended")

    def _processing_loop(self):
        """Main processing loop for transcription and analysis. THREAD SAFE."""
        logger.info(f"[THREAD: {threading.current_thread().name}] Processing loop started")

        # RACE CONDITION FIX: Use stop event instead of self.running
        while not self._stop_event.is_set():
            try:
                # Try to process any queued failed chunks if we're back online
                if self.is_online and self.failed_chunks:
                    self._retry_failed_chunks()

                # Get next audio chunk (with timeout to check stop flag)
                chunk = self.audio_capture.get_next_chunk(timeout=1)

                if not chunk:
                    # Check if we should stop
                    if self._stop_event.is_set():
                        break
                    continue

                # Update audio activity timestamp
                self.last_audio_activity = datetime.now()

                # Temporarily switch to processing state while transcribing chunk
                self._update_state(MeetingState.PROCESSING)

                # Attempt to transcribe and analyze with connection error handling
                success = self._process_chunk_with_retry(chunk)

                if success:
                    # Mark as online if we succeeded
                    if not self.is_online:
                        self._handle_connection_restored()

                # Return to recording state (unless stop was called)
                if not self._stop_event.is_set():
                    self._update_state(MeetingState.RECORDING)

            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                time.sleep(1)

        logger.info(f"[THREAD: {threading.current_thread().name}] Processing loop ended")

    def _process_chunk_with_retry(self, chunk: dict) -> bool:
        """
        Process a chunk with network error handling.

        Returns:
            True if successful, False if failed due to connection
        """
        try:
            # Transcribe audio chunk
            logger.info(f"Transcribing chunk: {chunk['filename'].name}")
            transcription_result = self.transcriber.transcribe_chunk(chunk)

            if transcription_result and transcription_result['text']:
                # Save transcription (with memory management)
                self.transcriptions.append(transcription_result)
                self.transcription_count += 1

                # Analyze transcription
                logger.info("Analyzing transcription...")
                analysis = self.analyzer.analyze_chunk(transcription_result['text'])

                if analysis:
                    # Save analysis (with memory management)
                    self.analyses.append({
                        'timestamp': datetime.now(),
                        'analysis': analysis
                    })
                    self.analysis_count += 1

                    # Send notifications for new insights
                    self._send_notifications(analysis)

                # MEMORY LEAK FIX: Stream to disk and trim memory every N chunks
                if self.transcription_count % self.chunks_between_disk_flush == 0:
                    self._stream_to_disk()
                    self._trim_memory()
                else:
                    logger.warning("Analysis failed for chunk")

                return True
            else:
                logger.warning("Transcription failed or empty for chunk")
                return False

        except Exception as e:
            # Check if this is a network-related error
            if self._is_network_error(e):
                logger.warning(f"Network error detected: {e}")
                self._handle_connection_lost(chunk)
                return False
            else:
                # Non-network error, just log and continue
                logger.error(f"Error processing chunk: {e}")
                return False

    def _is_network_error(self, error: Exception) -> bool:
        """Check if an error is network-related."""
        error_indicators = [
            'connection',
            'network',
            'timeout',
            'unreachable',
            'dns',
            'socket',
            'ssl',
            'certificate',
            'getaddrinfo',
            'http',
            'api'
        ]

        error_str = str(error).lower()
        error_type = type(error).__name__.lower()

        return any(indicator in error_str or indicator in error_type
                   for indicator in error_indicators)

    def _handle_connection_lost(self, chunk: dict):
        """Handle loss of internet connection."""
        was_online = self.is_online
        self.is_online = False

        # Queue chunk for retry
        self.failed_chunks.append(chunk)
        logger.info(f"Queued chunk for retry. Queue size: {len(self.failed_chunks)}")

        # Notify user if this is the first time we've lost connection
        if was_online:
            self.last_connection_notification = datetime.now()
            # if self.notifier:
            #     self.notifier.notify_error(
            #         "Internet connection lost. Recording continues, but live notes are paused."
            #     )
            logger.warning("Connection lost - live transcription/analysis disabled")

    def _handle_connection_restored(self):
        """Handle restoration of internet connection."""
        self.is_online = True
        # if self.notifier:
        #     self.notifier.notify_status(
        #         f"Connection restored! Processing {len(self.failed_chunks)} queued chunks..."
        #     )
        logger.info("Connection restored - resuming live processing")

    def _retry_failed_chunks(self):
        """Retry processing failed chunks after connection is restored."""
        if not self.failed_chunks:
            return

        logger.info(f"Retrying {len(self.failed_chunks)} failed chunks...")

        # Process up to 3 chunks at a time to avoid overwhelming the APIs
        chunks_to_retry = self.failed_chunks[:3]
        self.failed_chunks = self.failed_chunks[3:]

        for chunk in chunks_to_retry:
            try:
                success = self._process_chunk_with_retry(chunk)
                if not success:
                    # If it failed again, it will be re-queued by _process_chunk_with_retry
                    break
            except Exception as e:
                logger.error(f"Error retrying chunk: {e}")
                # Re-queue for next attempt
                self.failed_chunks.append(chunk)

    def _process_remaining_chunks(self):
        """Process any remaining audio chunks in the queue."""
        logger.info("Processing remaining chunks...")

        # Set a time budget for processing remaining chunks (15 seconds max)
        start_time = time.time()
        max_duration = 15.0  # seconds
        processed_count = 0
        skipped_count = 0

        while True:
            # Check if we've exceeded time budget
            elapsed = time.time() - start_time
            if elapsed > max_duration:
                logger.warning(f"Remaining chunks processing timeout after {elapsed:.1f}s - skipping rest")
                break

            chunk = self.audio_capture.get_next_chunk(timeout=0.1)
            if not chunk:
                break

            try:
                # Check time again before starting transcription
                if time.time() - start_time > max_duration:
                    logger.warning(f"Skipping chunk {chunk['filename'].name} - time budget exceeded")
                    skipped_count += 1
                    continue

                logger.info(f"Transcribing remaining chunk {processed_count + 1}: {chunk['filename'].name}")
                transcription_result = self.transcriber.transcribe_chunk(chunk)

                if transcription_result and transcription_result['text']:
                    self.transcriptions.append(transcription_result)
                    processed_count += 1
                    logger.info(f"✓ Remaining chunk transcribed ({len(transcription_result['text'])} chars)")

                    analysis = self.analyzer.analyze_chunk(transcription_result['text'])
                    if analysis:
                        self.analyses.append({
                            'timestamp': datetime.now(),
                            'analysis': analysis
                        })
                        logger.info(f"✓ Remaining chunk analyzed")
                else:
                    logger.warning(f"Remaining chunk transcription was empty or failed")

            except Exception as e:
                logger.error(f"Error processing remaining chunk: {e}")
                skipped_count += 1

        logger.info(f"✓ Finished remaining chunks: processed {processed_count}, skipped {skipped_count}. Total transcriptions now: {len(self.transcriptions)}")

    def _send_notifications(self, analysis: dict):
        """Send notifications based on analysis results."""
        # Get current transcription (just completed)
        current_transcription = self.transcriptions[-1] if self.transcriptions else None

        # Extract audio snippets for action items (but don't notify)
        for item in analysis.get('action_items', []):
            # Extract audio snippet if enabled
            if self.snippet_extractor and current_transcription and Config.SNIPPET_ENABLED:
                try:
                    snippet_path = self.snippet_extractor.extract_snippet_for_action_item(
                        action_item=item,
                        transcription=current_transcription,
                        before_duration=Config.SNIPPET_BEFORE_DURATION,
                        after_duration=Config.SNIPPET_AFTER_DURATION
                    )

                    if snippet_path:
                        # Store snippet reference (both hash-based and direct)
                        import hashlib
                        action_item_id = hashlib.md5(
                            f"{item['item']}_{item.get('assignee', '')}".encode()
                        ).hexdigest()[:8]
                        self.action_item_snippets[action_item_id] = snippet_path

                        # Also store with full action item info for easier matching
                        self.action_items_with_snippets.append({
                            'text': item['item'],
                            'assignee': item.get('assignee', ''),
                            'snippet_path': snippet_path
                        })
                        logger.info(f"Saved snippet for action item: {snippet_path.name}")

                except Exception as e:
                    logger.error(f"Failed to extract snippet: {e}", exc_info=True)

        # Don't send notifications for action items and decisions - too spammy
        # User will see them in the final summary

    def _on_audio_frame(self, audio_data: bytes):
        """
        Handle raw audio frames for streaming transcription.

        Buffers frames to meet AssemblyAI's minimum duration requirement (50ms).
        At 48000Hz, 2048 bytes = 21.3ms (too short), so we buffer ~3 frames = 64ms.

        Args:
            audio_data: Raw audio bytes from microphone (typically 2048 bytes = 21.3ms at 48000Hz)
        """
        # Initialize on first call
        if not hasattr(self, '_audio_frame_count'):
            self._audio_frame_count = 0
            self._streaming_buffer = []  # Buffer for combining small frames into 50ms+ chunks
            self._streaming_buffer_size = 0
            self.MIN_CHUNK_BYTES = 4800  # ~50ms at 48000Hz = 4800 bytes minimum
            logger.info("Audio frame callback initialized - will buffer frames to 50ms minimum")

        self._audio_frame_count += 1
        if self._audio_frame_count in [1, 10, 100]:
            logger.info(f"Audio frames received: {self._audio_frame_count} (size: {len(audio_data)} bytes)")

        # Don't buffer new audio after stop has been requested
        if self._stop_event.is_set():
            return

        try:
            if not self.streaming_transcriber or not self.streaming_transcriber.is_streaming:
                # Streaming not ready yet, skip this frame
                if self._audio_frame_count == 1:
                    logger.warning("Streaming not ready yet, dropping audio frames until ready")
                return

            # Add frame to buffer
            self._streaming_buffer.append(audio_data)
            self._streaming_buffer_size += len(audio_data)

            # Send when we have enough data (50ms minimum = ~4800 bytes at 48000Hz)
            if self._streaming_buffer_size >= self.MIN_CHUNK_BYTES:
                # Combine buffered frames
                combined_chunk = b''.join(self._streaming_buffer)

                # Log first few sends
                if self._audio_frame_count in [1, 10, 100]:
                    duration_ms = (len(combined_chunk) / 2) / 48000 * 1000  # 16-bit = 2 bytes per sample
                    logger.info(f"Sending {len(combined_chunk)} bytes (~{duration_ms:.1f}ms) to AssemblyAI")

                # Send to AssemblyAI
                self.streaming_transcriber.stream_audio(combined_chunk)

                # Clear buffer
                self._streaming_buffer = []
                self._streaming_buffer_size = 0

        except Exception as e:
            # Log first error, then throttle to avoid spam
            if not hasattr(self, '_streaming_error_logged'):
                logger.error(f"Streaming audio failed: {e}", exc_info=True)
                self._streaming_error_logged = True

    def _on_streaming_transcript(self, text: str, is_final: bool):
        """
        Handle streaming transcript updates.

        Args:
            text: Transcript text
            is_final: True if this is a final transcript, False if partial
        """
        # Don't process new transcripts after stop has been requested
        if self._stop_event.is_set():
            return

        try:
            if is_final:
                # Append final transcript to accumulated text
                self.streaming_transcript += text + " "
                logger.debug(f"Streaming final: {text}")

                # Process for live action item detection
                if self.live_action_notifier and self.live_action_notifier.is_enabled():
                    # TODO: Extract speaker label if available from AssemblyAI streaming
                    speaker = "Unknown"  # Streaming API doesn't provide speaker labels yet
                    self.live_action_notifier.process_transcript_chunk(text, speaker)
            else:
                # Just log partial transcripts for now
                logger.debug(f"Streaming partial: {text}")

        except Exception as e:
            logger.error(f"Error handling streaming transcript: {e}")

    def _ensure_wav(self, audio_file: Path) -> Optional[Path]:
        """Return audio_file unchanged if WAV, otherwise convert to WAV in recordings dir."""
        if audio_file.suffix.lower() == '.wav':
            return audio_file

        # Step 1: check pydub is importable
        try:
            from pydub import AudioSegment
        except ImportError:
            logger.error(
                "pydub is not installed. Run: pip install pydub"
            )
            return None

        # Step 2: attempt conversion — ffmpeg errors surface here, not at import
        try:
            logger.info(f"Converting {audio_file.suffix} to WAV...")
            wav_path = Config.RECORDINGS_DIR / f"upload_{self.meeting_id}.wav"
            audio = AudioSegment.from_file(str(audio_file))
            audio.export(str(wav_path), format='wav')
            logger.info(f"Converted to WAV: {wav_path}")
            return wav_path

        except FileNotFoundError as e:
            if 'ffmpeg' in str(e).lower() or 'avconv' in str(e).lower():
                logger.error(
                    "ffmpeg not found — pydub requires ffmpeg to convert audio files.\n"
                    "  Install ffmpeg and make sure it is on PATH.\n"
                    "  To check whether your venv can see it, run:\n"
                    "    python -c \"import subprocess; print(subprocess.run(['ffmpeg', '-version'], capture_output=True).stdout.decode()[:80])\""
                )
            else:
                logger.error(f"File not found during audio conversion: {e}")
            return None

        except Exception as e:
            err = str(e).lower()
            if 'ffmpeg' in err or 'avconv' in err or 'couldn\'t find' in err:
                logger.error(
                    f"ffmpeg error during conversion: {e}\n"
                    "  Ensure ffmpeg is installed and accessible from the venv's PATH.\n"
                    "  To check: python -c \"import subprocess; print(subprocess.run(['ffmpeg', '-version'], capture_output=True).stdout.decode()[:80])\""
                )
            else:
                logger.error(f"Failed to convert {audio_file.suffix} to WAV: {e}")
            return None

    def _split_audio_into_chunks(self, wav_file: Path, chunk_duration: int) -> list:
        """
        Split a WAV file into chunk dicts compatible with _process_chunk_with_retry().

        Chunk filenames follow the live-recording naming convention
        (chunk_YYYYMMDD_HHMMSS.wav) so _create_complete_recording() picks them up.
        """
        import wave as _wave
        chunks = []
        with _wave.open(str(wav_file), 'rb') as wf:
            params = wf.getparams()
            sample_rate = params.framerate
            n_channels = params.nchannels
            sampwidth = params.sampwidth
            frames_per_chunk = sample_rate * chunk_duration

            chunk_index = 0
            while True:
                frames = wf.readframes(frames_per_chunk)
                if not frames:
                    break

                # Assign timestamps starting from meeting_start_time
                chunk_ts = self.meeting_start_time + timedelta(seconds=chunk_index * chunk_duration)
                chunk_path = Config.RECORDINGS_DIR / f"chunk_{chunk_ts.strftime('%Y%m%d_%H%M%S')}.wav"

                with _wave.open(str(chunk_path), 'wb') as out:
                    out.setparams(params)
                    out.writeframes(frames)

                # Actual duration in seconds for this chunk (last chunk may be shorter)
                actual_secs = len(frames) / (sample_rate * n_channels * sampwidth)
                chunks.append({
                    'filename': chunk_path,
                    'duration': actual_secs,
                    'timestamp': chunk_ts,
                    'chunk_timestamp': chunk_ts,
                    'sample_rate': sample_rate,
                    'channels': n_channels,
                })
                chunk_index += 1

        logger.info(f"Split {wav_file.name} into {len(chunks)} chunks (~{chunk_duration}s each)")
        return chunks

    def process_uploaded_file(
        self,
        audio_path: Path,
        status_callback: Optional[Callable] = None
    ) -> Optional[str]:
        """
        Process an uploaded audio file through the same full pipeline as live recording:
          audio → 30-second WAV chunks → transcribe_chunk() → analyze_chunk()
          → _generate_meeting_summary() (includes Haiku ASR cleanup + HTML output)

        Args:
            audio_path: Path to the audio file (WAV, M4A, MP3, etc.)
            status_callback: Optional callable(step: str, done: int, total: int)

        Returns:
            Path to the HTML summary or None on failure
        """
        self._reset()
        self.meeting_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.meeting_start_time = datetime.now()
        Config.create_directories()
        self._update_state(MeetingState.PROCESSING)

        def _status(step: str, done: int = 0, total: int = 0):
            suffix = f" ({done}/{total})" if total else ""
            logger.info(f"[upload] {step}{suffix}")
            if status_callback:
                status_callback(step, done, total)

        try:
            _status("Converting audio to WAV if needed...")
            wav_file = self._ensure_wav(audio_path)
            if not wav_file:
                logger.error("Could not obtain WAV for processing")
                self._update_state(MeetingState.ERROR)
                return None

            _status("Splitting into 30-second chunks...")
            chunks = self._split_audio_into_chunks(wav_file, Config.AUDIO_CHUNK_DURATION)
            if not chunks:
                logger.error("No chunks produced from audio file")
                self._update_state(MeetingState.ERROR)
                return None

            logger.info(f"Processing {len(chunks)} chunks from {audio_path.name}")
            for i, chunk in enumerate(chunks):
                _status(f"Transcribing + analyzing chunk", i + 1, len(chunks))
                self._process_chunk_with_retry(chunk)

            _status("Generating summary (Haiku cleanup + Sonnet)...")
            summary_path = self._generate_meeting_summary()

            if summary_path:
                self._save_to_memory()
                _status("Complete!")

            self._update_state(MeetingState.IDLE)
            return summary_path

        except Exception as e:
            logger.error(f"Error processing uploaded file: {e}", exc_info=True)
            self._update_state(MeetingState.ERROR)
            return None

    def _create_complete_recording(self) -> Optional[Path]:
        """Combine audio chunks from THIS meeting session into a complete recording."""
        try:
            import wave

            # Filter chunks to only those recorded during this meeting session.
            # Chunk names are chunk_YYYYMMDD_HHMMSS.wav; parse timestamp and compare
            # against meeting_start_time so leftover chunks from previous sessions
            # are never included (prevents inflated durations like 2450s for a 1-min meeting).
            all_chunks = sorted(Config.RECORDINGS_DIR.glob("chunk_*.wav"))
            chunk_files = []
            for f in all_chunks:
                try:
                    ts = datetime.strptime(f.stem, "chunk_%Y%m%d_%H%M%S")
                    if self.meeting_start_time and ts >= self.meeting_start_time:
                        chunk_files.append(f)
                except ValueError:
                    pass  # skip files that don't match the naming pattern

            if not chunk_files:
                logger.warning("No chunk files found for current meeting session")
                return None

            logger.info(f"Combining {len(chunk_files)} chunks for meeting {self.meeting_id} "
                        f"(skipped {len(all_chunks) - len(chunk_files)} chunks from previous sessions)")

            # Create complete recording filename
            complete_filename = f"complete_recording_{self.meeting_id}.wav"
            complete_path = Config.MEETINGS_DIR / complete_filename

            # Combine all chunks
            with wave.open(str(complete_path), 'wb') as output_wav:
                for i, chunk_file in enumerate(chunk_files):
                    with wave.open(str(chunk_file), 'rb') as chunk_wav:
                        if i == 0:
                            # Set parameters from first chunk
                            output_wav.setparams(chunk_wav.getparams())
                        # Write audio data
                        output_wav.writeframes(chunk_wav.readframes(chunk_wav.getnframes()))

            logger.info(f"Created complete recording: {complete_path}")
            return complete_path

        except Exception as e:
            logger.error(f"Failed to create complete recording: {e}", exc_info=True)
            return None

    def _generate_meeting_summary(self) -> Optional[Path]:
        """Generate and save meeting summary."""
        try:
            logger.info("Generating meeting summary...")

            # MEMORY LEAK FIX: Load all data from disk before generating summary
            all_transcriptions, all_analyses = self._load_from_disk()
            logger.info(f"Summary will use {len(all_transcriptions)} transcriptions, {len(all_analyses)} analyses")

            # Layer 1: Rebuild conversation_history in CHRONOLOGICAL ORDER from all transcriptions.
            #
            # Previous bug: _update_context() trims conversation_history to the last 10 chunks.
            # The old "append missing texts" loop left those 10 recent chunks at the FRONT of
            # the list, then tacked all the earlier chunks on at the END. So conversation_history
            # looked like [chunk_103..chunk_113, chunk_1, chunk_2, ..., chunk_102].
            # generate_summary() joins this list top-to-bottom, and the HTML transcript div
            # renders the joined string from top to bottom — meaning the LAST 2-3 minutes of
            # the meeting appeared at the top of the visible area, making it look like the
            # transcript was truncated to only the final few minutes.
            #
            # Fix: sort all_transcriptions by chunk_timestamp, deduplicate by text content,
            # and replace conversation_history entirely with the correctly ordered sequence.
            if all_transcriptions:
                def _chunk_ts(t):
                    ts = t.get('chunk_timestamp')
                    if isinstance(ts, datetime):
                        return ts
                    raw = t.get('timestamp')
                    if isinstance(raw, str):
                        try:
                            return datetime.fromisoformat(raw)
                        except ValueError:
                            pass
                    return datetime.max  # unknown → sort to end (most recent)

                sorted_trans = sorted(all_transcriptions, key=_chunk_ts)
                seen_texts: set = set()
                ordered_texts: list = []
                for t in sorted_trans:
                    text = t.get('text', '').strip()
                    if text and text not in seen_texts:
                        seen_texts.add(text)
                        ordered_texts.append(text)

                prev_len = len(self.analyzer.conversation_history)
                self.analyzer.conversation_history = ordered_texts
                logger.info(
                    f"Layer 1: Rebuilt conversation_history in chronological order — "
                    f"{len(ordered_texts)} unique segments "
                    f"(prev in-memory: {prev_len}, raw from disk+memory: {len(all_transcriptions)})"
                )

            # BLANK SUMMARY FIX — Layer 2: chunk transcription itself was still in-flight
            # (transcribe_chunk() / AssemblyAI batch API hadn't returned yet), so all_transcriptions
            # is also empty. Fall back to self.streaming_transcript, which is the live text
            # captured by AssemblyAI streaming v3 throughout the entire recording session.
            # streaming_transcript is fully populated by the time we reach here: stop_streaming()
            # was called ~45s ago and no new streaming callbacks can arrive after _stop_event is set.
            if not self.analyzer.conversation_history and self.streaming_transcript.strip():
                self.analyzer.conversation_history.append(self.streaming_transcript.strip())
                logger.info(f"Using streaming transcript as summary fallback "
                            f"({len(self.streaming_transcript.strip())} chars — "
                            f"chunk transcription was still in-flight at summary time)")

            # COVERAGE FIX — Layer 3: Supplement sparse batch transcription with streaming.
            # Streaming runs continuously for the full session; batch chunks can be missed if
            # AssemblyAI was slow and the processing thread was still mid-call when stop was
            # clicked. When streaming has substantially more content than what batch produced,
            # it covers the transcript gaps. Claude's summary prompt synthesizes both sources.
            if self.streaming_transcript.strip():
                batch_chars = sum(len(s) for s in self.analyzer.conversation_history)
                streaming_chars = len(self.streaming_transcript.strip())
                if streaming_chars > batch_chars * 1.2 + 50:
                    self.analyzer.conversation_history.append(self.streaming_transcript.strip())
                    logger.info(f"COVERAGE Layer 3: Added streaming transcript to supplement sparse batch "
                                f"({streaming_chars} streaming chars vs {batch_chars} batch chars)")

            # Log final state so we can confirm which path was taken
            if not self.analyzer.conversation_history:
                logger.warning("No transcript data available for summary (no chunks, no streaming text)")
            else:
                logger.info(f"Summary will use {len(self.analyzer.conversation_history)} transcript segment(s) "
                            f"from conversation_history")

            # Create complete audio recording
            complete_recording_path = self._create_complete_recording()

            # Calculate average transcription confidence (from all data).
            # None when the model doesn't return confidence scores (e.g. gpt-4o-transcribe).
            avg_confidence = None
            if all_transcriptions:
                confidences = [t['confidence'] for t in all_transcriptions if t.get('confidence') is not None]
                if confidences:
                    avg_confidence = sum(confidences) / len(confidences)

            # Collect word-level confidence data from all transcriptions.
            # IMPORTANT: Disk-streamed transcriptions do NOT carry the 'words' field
            # (only 'text', 'timestamp', 'confidence' are saved to disk). For long
            # meetings the disk holds most chunks, so only the last ~10 in-memory
            # chunks will have word data. Passing partial word data to generate_summary()
            # causes _annotate_transcript_confidence() to RECONSTRUCT the transcript
            # from those words only, silently discarding the rest of the meeting.
            # Only pass word data when it covers most of the meeting (>= 80%).
            all_words = []
            for transcription in all_transcriptions:
                if 'words' in transcription and transcription['words']:
                    all_words.append(transcription['words'])

            chunks_with_words = len(all_words)
            total_chunks = len(all_transcriptions)
            words_coverage = chunks_with_words / total_chunks if total_chunks else 0
            logger.info(
                f"[transcript] word data: {chunks_with_words}/{total_chunks} chunks "
                f"have word-level data ({words_coverage:.0%} coverage)"
            )
            if all_words and words_coverage < 0.8:
                logger.warning(
                    f"[transcript] Word coverage {words_coverage:.0%} < 80% — "
                    f"skipping confidence annotation to avoid truncating the transcript. "
                    f"(Disk-flushed chunks don't carry word data; save 'words' to disk "
                    f"to enable annotation for long meetings.)"
                )
            transcription_words_arg = all_words if (all_words and words_coverage >= 0.8) else None

            # Generate AI summary with confidence score, word data, and snippet links
            summary = self.analyzer.generate_summary(
                transcription_confidence=avg_confidence,
                transcription_words=transcription_words_arg,
                action_item_snippets=self.action_item_snippets if self.action_item_snippets else None
            )

            # Create summary file
            summary_filename = f"meeting_{self.meeting_id}.md"
            summary_path = Config.MEETINGS_DIR / summary_filename

            # Add metadata header
            _product_label = f"{Config.PRODUCT_NAME} " if Config.PRODUCT_NAME else ""
            _quality_line = f"Transcription Quality: {avg_confidence:.1%}\n" if avg_confidence is not None else ""
            metadata = f"""{_product_label}MEETING SUMMARY
Date: {self.meeting_start_time.strftime('%Y-%m-%d %H:%M')}
{_quality_line}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""

            # Write summary
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(metadata + summary)

            # Extract timestamps for action items (for Play buttons)
            self._extract_action_item_timestamps(summary, all_transcriptions)

            # Generate HTML version with embedded audio.
            # Pass the annotated+cleaned full transcript directly so the HTML always
            # contains the complete text — Claude's output is capped at max_tokens and
            # would truncate long meetings if we relied on it to reproduce the transcript.
            logger.info(f"DEBUG: Passing full_transcript to HTML generator, length={len(self.analyzer.last_full_transcript or '')} chars")
            html_path = self.html_generator.generate_html(
                markdown_summary=metadata + summary,
                snippet_paths=self.action_item_snippets,
                meeting_id=self.meeting_id,
                meeting_dir=Config.MEETINGS_DIR,
                complete_recording_path=complete_recording_path,
                action_items_with_snippets=self.action_items_with_snippets,
                full_transcript=self.analyzer.last_full_transcript or None
            )

            # Copy HTML and audio to user's Summaries folder (PORTABLE - no hard-coded paths)
            try:
                import shutil
                if html_path:
                    # Use Config.SUMMARIES_DIR which points to user's Documents/Pilot/summaries
                    summaries_dir = Config.SUMMARIES_DIR
                    summaries_dir.mkdir(parents=True, exist_ok=True)

                    # Copy HTML
                    summary_dest = summaries_dir / f"Meeting_Summary_{self.meeting_id}.html"
                    shutil.copy(html_path, summary_dest)
                    logger.info(f"Copied HTML summary to: {summary_dest}")

                    # Copy complete recording
                    if complete_recording_path and complete_recording_path.exists():
                        audio_dest = summaries_dir / complete_recording_path.name
                        shutil.copy(complete_recording_path, audio_dest)
                        logger.info(f"Copied audio recording to: {audio_dest}")

                    # Copy snippet files
                    snippets_dest_dir = summaries_dir / "snippets"
                    snippets_dest_dir.mkdir(exist_ok=True)
                    snippet_count = 0

                    for item in self.action_items_with_snippets:
                        snippet_path = item.get('snippet_path')
                        if snippet_path and snippet_path.exists():
                            snippet_dest = snippets_dest_dir / snippet_path.name
                            shutil.copy(snippet_path, snippet_dest)
                            snippet_count += 1

                    logger.info(f"Copied {snippet_count} snippet files to summaries/snippets")

                    # Update return path to summaries location
                    html_path = summary_dest
            except Exception as e:
                logger.warning(f"Could not copy to summaries folder: {e}")

            # Also save raw data as JSON (using all data from disk + memory)
            data_path = Config.MEETINGS_DIR / f"meeting_{self.meeting_id}.json"
            meeting_data = {
                'meeting_id': self.meeting_id,
                'start_time': self.meeting_start_time.isoformat(),
                'duration': self._get_meeting_duration(),
                'transcriptions': [
                    {
                        'text': t['text'],
                        'timestamp': t.get('chunk_timestamp').isoformat() if t.get('chunk_timestamp') else t.get('timestamp')
                    }
                    for t in all_transcriptions
                ],
                'analyses': [
                    {
                        'timestamp': a.get('timestamp').isoformat() if isinstance(a.get('timestamp'), datetime) else a.get('timestamp'),
                        'analysis': a['analysis']
                    }
                    for a in all_analyses
                ]
            }

            with open(data_path, 'w', encoding='utf-8') as f:
                json.dump(meeting_data, f, indent=2)

            logger.info(f"Meeting summary saved: {summary_path}")
            if html_path:
                logger.info(f"HTML summary saved: {html_path}")
            return html_path if html_path else summary_path

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return None

    def _extract_action_item_timestamps(self, summary: str, transcriptions: list = None):
        """Extract timestamps for action items from summary and transcription."""
        import re

        # Use provided transcriptions or fallback to self.transcriptions
        transcriptions_to_use = transcriptions if transcriptions is not None else self.transcriptions

        # Combine all word-level timestamps from all chunks
        all_words = []
        for transcription in transcriptions_to_use:
            if 'words' in transcription and transcription['words']:
                all_words.extend(transcription['words'])

        if not all_words:
            logger.warning("No word-level timestamps available")
            return

        # Parse action items from summary
        action_items_section = False
        for line in summary.split('\n'):
            line_stripped = line.strip().lstrip('#').strip()

            if line_stripped == 'ACTION ITEMS':
                action_items_section = True
                continue

            if line_stripped in ['DECISIONS', 'ITEMS REQUIRING CLARIFICATION', 'MEETING SYNOPSIS']:
                action_items_section = False
                continue

            if action_items_section and line.strip().startswith('-'):
                match = re.match(r'-\s*\*\*([^*]+)\*\*:\s*(.+?)(?:\s*\||$)', line)
                if match:
                    assignee = match.group(1).strip()
                    action_text = match.group(2).strip()

                    try:
                        # Find timestamps in transcription
                        from src.audio_snippet_extractor import AudioSnippetExtractor
                        snippet_extractor = AudioSnippetExtractor(
                            recordings_dir=Config.RECORDINGS_DIR,
                            snippets_dir=Config.SNIPPETS_DIR
                        )

                        start_time, end_time = snippet_extractor._find_action_item_in_transcription(
                            action_item_text=action_text,
                            transcription_words=all_words
                        )

                        if start_time is not None:
                            # Add to action_items_with_snippets for HTML generation
                            self.action_items_with_snippets.append({
                                'text': action_text,
                                'assignee': assignee,
                                'snippet_path': None,  # No snippet file, using Play buttons
                                'start_time': start_time,
                                'end_time': end_time
                            })
                            logger.info(f"Found timestamp for action: {action_text[:50]}... at {start_time:.1f}s")

                    except Exception as e:
                        logger.warning(f"Failed to extract timestamp for action item: {e}")

    def _save_to_memory(self):
        """Save current meeting to persistent memory."""
        try:
            meeting_data = {
                'meeting_id': self.meeting_id,
                'start_time': self.meeting_start_time.isoformat() if self.meeting_start_time else None,
                'duration': self._get_meeting_duration(),
                'analyses': self.analyses,
                'summary': ""  # Will be populated if we read the summary file
            }

            # Try to read the summary for storage
            if self.meeting_id:
                summary_path = Config.MEETINGS_DIR / f"meeting_{self.meeting_id}.md"
                if summary_path.exists():
                    with open(summary_path, 'r', encoding='utf-8') as f:
                        meeting_data['summary'] = f.read()

            self.memory.add_meeting(meeting_data)
            logger.info("Meeting saved to persistent memory")

        except Exception as e:
            logger.error(f"Error saving to memory: {e}")

    def _get_meeting_duration(self) -> str:
        """Get formatted meeting duration."""
        if not self.meeting_start_time:
            return "Unknown"

        duration = datetime.now() - self.meeting_start_time
        hours = int(duration.total_seconds() // 3600)
        minutes = int((duration.total_seconds() % 3600) // 60)

        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    def _update_state(self, new_state: MeetingState):
        """Update meeting state and notify callback. THREAD SAFE."""
        callback_to_call = None
        state_changed = False

        with self._state_lock:
            if self.state != new_state:
                old_state = self.state
                self.state = new_state
                state_changed = True
                logger.info(f"[THREAD: {threading.current_thread().name}] State changed: {old_state.value} -> {new_state.value}")

                # Callback outside of lock to avoid deadlocks
                callback_to_call = self.state_change_callback

        # Call callback outside lock (only if state changed)
        if state_changed and callback_to_call:
            try:
                callback_to_call(new_state)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

    def _stream_to_disk(self):
        """Stream transcriptions and analyses to disk to free memory."""
        if not self.meeting_id:
            return

        try:
            # Create streaming data directory
            streaming_dir = Config.MEETINGS_DIR / f"meeting_{self.meeting_id}_chunks"
            streaming_dir.mkdir(exist_ok=True)

            # Save transcriptions to disk
            if self.transcriptions:
                transcription_file = streaming_dir / f"transcriptions_{self.transcription_count}.json"
                with open(transcription_file, 'w', encoding='utf-8') as f:
                    json.dump([
                        {
                            'text': t['text'],
                            'timestamp': t['chunk_timestamp'].isoformat() if 'chunk_timestamp' in t else None,
                            'confidence': t.get('confidence')
                        }
                        for t in self.transcriptions
                    ], f, indent=2)
                logger.debug(f"Streamed {len(self.transcriptions)} transcriptions to disk")

            # Save analyses to disk
            if self.analyses:
                analysis_file = streaming_dir / f"analyses_{self.analysis_count}.json"
                with open(analysis_file, 'w', encoding='utf-8') as f:
                    json.dump([
                        {
                            'timestamp': a['timestamp'].isoformat(),
                            'analysis': a['analysis']
                        }
                        for a in self.analyses
                    ], f, indent=2)
                logger.debug(f"Streamed {len(self.analyses)} analyses to disk")

        except Exception as e:
            logger.error(f"Error streaming to disk: {e}")

    def _trim_memory(self):
        """Keep only last N chunks in memory to prevent memory leaks."""
        try:
            # Trim transcriptions
            if len(self.transcriptions) > self.max_chunks_in_memory:
                removed = len(self.transcriptions) - self.max_chunks_in_memory
                self.transcriptions = self.transcriptions[-self.max_chunks_in_memory:]
                logger.info(f"Trimmed {removed} transcriptions from memory (kept last {self.max_chunks_in_memory})")

            # Trim analyses
            if len(self.analyses) > self.max_chunks_in_memory:
                removed = len(self.analyses) - self.max_chunks_in_memory
                self.analyses = self.analyses[-self.max_chunks_in_memory:]
                logger.info(f"Trimmed {removed} analyses from memory (kept last {self.max_chunks_in_memory})")

            # Log memory usage
            import sys
            transcription_size = sum(sys.getsizeof(t) for t in self.transcriptions)
            analysis_size = sum(sys.getsizeof(a) for a in self.analyses)
            logger.info(f"Memory usage: transcriptions={transcription_size/1024:.1f}KB, analyses={analysis_size/1024:.1f}KB")

        except Exception as e:
            logger.error(f"Error trimming memory: {e}")

    def _load_from_disk(self) -> tuple:
        """
        Load all transcriptions and analyses from disk for final summary generation.
        Also includes any in-memory data not yet saved to disk (e.g., from _process_remaining_chunks).

        Returns:
            (transcriptions, analyses) tuple with all data
        """
        if not self.meeting_id:
            return (self.transcriptions, self.analyses)

        try:
            streaming_dir = Config.MEETINGS_DIR / f"meeting_{self.meeting_id}_chunks"

            if not streaming_dir.exists():
                logger.info("No streaming data directory found, using in-memory data only")
                return (self.transcriptions, self.analyses)

            all_transcriptions = []
            all_analyses = []

            # Load all transcription files
            transcription_files = sorted(streaming_dir.glob("transcriptions_*.json"))
            for trans_file in transcription_files:
                with open(trans_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert timestamps back to datetime objects
                    for item in data:
                        if item.get('timestamp'):
                            item['chunk_timestamp'] = datetime.fromisoformat(item['timestamp'])
                    all_transcriptions.extend(data)

            # Load all analysis files
            analysis_files = sorted(streaming_dir.glob("analyses_*.json"))
            for analysis_file in analysis_files:
                with open(analysis_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert timestamps back to datetime objects
                    for item in data:
                        if item.get('timestamp'):
                            item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                    all_analyses.extend(data)

            # Include current in-memory data (e.g., from _process_remaining_chunks)
            disk_trans_count = len(all_transcriptions)
            disk_anal_count = len(all_analyses)
            all_transcriptions.extend(self.transcriptions)
            all_analyses.extend(self.analyses)

            logger.info(f"Loaded {disk_trans_count} transcriptions from disk + {len(self.transcriptions)} in-memory = {len(all_transcriptions)} total")
            logger.info(f"Loaded {disk_anal_count} analyses from disk + {len(self.analyses)} in-memory = {len(all_analyses)} total")
            return (all_transcriptions, all_analyses)

        except Exception as e:
            logger.error(f"Error loading from disk, using in-memory data: {e}")
            return (self.transcriptions, self.analyses)

    def _reset(self):
        """Reset manager state for next meeting."""
        self.state = MeetingState.IDLE
        self._stopping = False
        self.meeting_id = None
        self.meeting_start_time = None
        self.transcriptions.clear()
        self.analyses.clear()
        self.transcription_count = 0
        self.analysis_count = 0
        self.action_item_snippets.clear()
        self.action_items_with_snippets.clear()
        self.failed_chunks.clear()
        self.is_online = True
        self.last_connection_notification = None
        self.streaming_transcript = ""
        self.analyzer.reset()

    def get_state(self) -> MeetingState:
        """Get current meeting state. THREAD SAFE."""
        with self._state_lock:
            return self.state

    def _is_state(self, *states: MeetingState) -> bool:
        """Check if current state matches any of the given states. THREAD SAFE."""
        with self._state_lock:
            return self.state in states

    def get_meeting_info(self) -> dict:
        """Get current meeting information."""
        return {
            'meeting_id': self.meeting_id,
            'state': self.state.value,
            'start_time': self.meeting_start_time,
            'duration': self._get_meeting_duration() if self.meeting_start_time else None,
            'chunks_processed': len(self.transcriptions),
            'analyses': len(self.analyses)
        }

    def cleanup(self):
        """Cleanup resources with proper thread shutdown."""
        logger.info("Starting cleanup...")

        # Stop meeting if in progress
        if self.state != MeetingState.IDLE:
            logger.info("Stopping active meeting before cleanup...")
            self.stop_meeting()

        # Save any failed chunks to disk before exit
        if self.failed_chunks:
            logger.info(f"Persisting {len(self.failed_chunks)} failed chunks...")
            self._persist_failed_chunks()

        # Stop threads gracefully - RACE CONDITION FIX
        self._stop_event.set()  # Signal all threads to stop

        # Wait for processing thread to finish (with timeout)
        if self.processing_thread and self.processing_thread.is_alive():
            logger.info("Waiting for processing thread to finish...")
            self.processing_thread.join(timeout=5.0)
            if self.processing_thread.is_alive():
                logger.warning("Processing thread did not finish in time")

        # Wait for silence monitor thread
        if self.silence_monitor_thread and self.silence_monitor_thread.is_alive():
            logger.info("Waiting for silence monitor to finish...")
            self.silence_monitor_thread.join(timeout=2.0)
            if self.silence_monitor_thread.is_alive():
                logger.warning("Silence monitor did not finish in time")

        # Cleanup audio capture
        self.audio_capture.cleanup()

        logger.info("Meeting manager cleanup complete")

    def _persist_failed_chunks(self):
        """Save failed chunks to disk for later retry."""
        try:
            if not self.failed_chunks:
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            failed_chunks_file = Config.FAILED_CHUNKS_DIR / f"failed_chunks_{timestamp}.json"

            # Convert chunk data to serializable format
            chunks_data = []
            for chunk in self.failed_chunks:
                chunk_data = {
                    'filename': str(chunk['filename']),
                    'duration': chunk['duration'],
                    'timestamp': chunk['timestamp'].isoformat(),
                    'sample_rate': chunk.get('sample_rate', 48000),  # Fallback to 48kHz if not specified
                    'channels': chunk.get('channels', 1)  # Fallback to mono
                }
                chunks_data.append(chunk_data)

            with open(failed_chunks_file, 'w') as f:
                json.dump({
                    'meeting_id': self.meeting_id,
                    'saved_at': datetime.now().isoformat(),
                    'chunks': chunks_data
                }, f, indent=2)

            logger.info(f"Saved {len(chunks_data)} failed chunks to {failed_chunks_file}")

        except Exception as e:
            logger.error(f"Failed to persist failed chunks: {e}")

    def load_failed_chunks(self):
        """Load previously failed chunks from disk."""
        try:
            failed_files = list(Config.FAILED_CHUNKS_DIR.glob("failed_chunks_*.json"))

            if not failed_files:
                return []

            all_failed = []
            for file in failed_files:
                try:
                    with open(file, 'r') as f:
                        data = json.load(f)
                        for chunk_data in data.get('chunks', []):
                            # Reconstruct chunk dict
                            chunk = {
                                'filename': Path(chunk_data['filename']),
                                'duration': chunk_data['duration'],
                                'timestamp': datetime.fromisoformat(chunk_data['timestamp']),
                                'sample_rate': chunk_data.get('sample_rate'),
                                'channels': chunk_data.get('channels')
                            }
                            # Only add if file still exists
                            if chunk['filename'].exists():
                                all_failed.append(chunk)
                except Exception as e:
                    logger.error(f"Error loading failed chunks from {file}: {e}")

            if all_failed:
                logger.info(f"Loaded {len(all_failed)} previously failed chunks")

            return all_failed

        except Exception as e:
            logger.error(f"Error loading failed chunks: {e}")
            return []

    def retry_failed_chunks(self):
        """Retry processing previously failed chunks."""
        failed_chunks = self.load_failed_chunks()

        if not failed_chunks:
            logger.info("No failed chunks to retry")
            return 0

        logger.info(f"Retrying {len(failed_chunks)} failed chunks...")
        success_count = 0

        for chunk in failed_chunks:
            try:
                success = self._process_chunk_with_retry(chunk)
                if success:
                    success_count += 1
            except Exception as e:
                logger.error(f"Error retrying chunk {chunk['filename']}: {e}")

        logger.info(f"Successfully reprocessed {success_count}/{len(failed_chunks)} chunks")
        return success_count


def test_meeting_manager():
    """Test meeting manager functionality."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing Meeting Manager...")
    print("This will record for 30 seconds and process the audio.\n")

    # Validate configuration
    errors = Config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  ✗ {error}")
        print("\nPlease set up your .env file with API keys.")
        return

    manager = MeetingManager()

    def state_callback(state: MeetingState):
        print(f"State changed: {state.value}")

    try:
        # Start meeting
        print("Starting meeting...")
        if manager.start_meeting(callback=state_callback):
            print("✓ Meeting started\n")
            print("Recording... (30 seconds)")
            print("Play some audio or have a conversation.\n")

            # Record for 30 seconds
            time.sleep(30)

            # Stop meeting
            print("\nStopping meeting...")
            summary_path = manager.stop_meeting()

            if summary_path:
                print(f"\n✓ Meeting summary saved: {summary_path}")
                print(f"\nMeeting info:")
                info = manager.get_meeting_info()
                print(f"  Duration: {info['duration']}")
                print(f"  Chunks processed: {info['chunks_processed']}")
                print(f"  Analyses: {info['analyses']}")
            else:
                print("\n✗ Failed to generate summary")

        else:
            print("✗ Failed to start meeting")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        manager.stop_meeting()
    except Exception as e:
        print(f"\n✗ Error: {e}")
    finally:
        manager.cleanup()


if __name__ == '__main__':
    test_meeting_manager()
