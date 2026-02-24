"""Audio capture module using Windows WASAPI loopback."""

import pyaudiowpatch as pyaudio
import wave
import threading
import queue
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

from .config import Config

logger = logging.getLogger(__name__)


class AudioCapture:
    """Captures system audio using Windows WASAPI loopback."""

    def __init__(self, chunk_duration: int = None):
        """
        Initialize audio capture.

        Args:
            chunk_duration: Duration of each audio chunk in seconds (default from config)
        """
        self.chunk_duration = chunk_duration or Config.AUDIO_CHUNK_DURATION

        self.audio = pyaudio.PyAudio()
        self.stream: Optional[pyaudio.Stream] = None
        self.recording = False
        self.capture_thread: Optional[threading.Thread] = None

        # Queue for audio chunks (each chunk is ~30 seconds)
        self.chunk_queue = queue.Queue()

        # Buffer for current chunk
        self.current_chunk = []
        self.chunk_start_time = None

        # Stream parameters (set during recording based on device capabilities)
        # These will be auto-detected from the microphone (typically 48000 Hz, mono)
        self.stream_channels = None  # Will be set from device
        self.stream_sample_rate = None  # Will be set from device (e.g., 48000 Hz)

        # Optional callback for raw audio frames (for streaming transcription)
        self.audio_frame_callback: Optional[Callable] = None

    def get_default_microphone(self, device_index: Optional[int] = None) -> Optional[dict]:
        """
        Get the default microphone input device or specific device.

        Args:
            device_index: Optional specific device index to use (None for auto-detect)

        Returns:
            Device info dict or None if not found
        """
        try:
            if device_index is not None:
                # Use specific device
                device_info = self.audio.get_device_info_by_index(device_index)
                logger.info(f"Using specified microphone {device_index}: {device_info['name']}")
                return device_info

            # Auto-detect: Find best microphone (skip mappers, stereo mix, loopback)
            logger.info("Auto-detecting microphone...")
            candidates = []

            for i in range(self.audio.get_device_count()):
                info = self.audio.get_device_info_by_index(i)

                if info['maxInputChannels'] > 0:
                    name_lower = info['name'].lower()

                    # Skip these device types
                    skip_keywords = [
                        'stereo mix',
                        'loopback',
                        'mapper',  # Windows Sound Mapper
                        'wave',    # Microsoft Sound Mapper
                        'what u hear',
                        'wasapi',
                        'primary sound capture'
                    ]

                    if any(keyword in name_lower for keyword in skip_keywords):
                        logger.debug(f"Skipping {info['name']} (mapper/loopback device)")
                        continue

                    # Prioritize devices with "microphone" or "mic" in name
                    priority = 0
                    if 'microphone' in name_lower or 'mic' in name_lower:
                        priority = 2
                    elif 'audio' in name_lower or 'input' in name_lower:
                        priority = 1

                    candidates.append((priority, i, info))
                    logger.debug(f"Found input device: {info['name']} (priority: {priority})")

            if candidates:
                # Sort by priority (highest first) and pick best
                candidates.sort(reverse=True, key=lambda x: x[0])
                priority, idx, best_device = candidates[0]
                logger.info(f"Auto-detected microphone: {best_device['name']}")
                return best_device

            # Last resort: try default input device
            logger.warning("No suitable microphone found, trying default input...")
            default_input = self.audio.get_default_input_device_info()
            logger.info(f"Using default input: {default_input['name']}")
            return default_input

        except Exception as e:
            logger.error(f"Error finding microphone: {e}")
            return None

    def list_audio_devices(self):
        """List all available audio devices for debugging."""
        print("\n" + "="*60)
        print("AVAILABLE AUDIO DEVICES")
        print("="*60)

        for i in range(self.audio.get_device_count()):
            try:
                info = self.audio.get_device_info_by_index(i)
                device_type = []
                if info['maxInputChannels'] > 0:
                    device_type.append("INPUT")
                if info['maxOutputChannels'] > 0:
                    device_type.append("OUTPUT")

                print(f"\nDevice {i}: {info['name']}")
                print(f"  Type: {' / '.join(device_type)}")
                print(f"  Input Channels: {info['maxInputChannels']}")
                print(f"  Output Channels: {info['maxOutputChannels']}")
                print(f"  Sample Rate: {info['defaultSampleRate']} Hz")

            except Exception as e:
                print(f"\nDevice {i}: Error - {e}")

        print("\n" + "="*60)
        print("To use a specific device, add to config.ini:")
        print("  [Audio]")
        print("  microphone_device_index = <device_number>")
        print("="*60 + "\n")

    def get_loopback_device(self) -> Optional[dict]:
        """
        Find the Windows WASAPI loopback device.

        Returns:
            Device info dict or None if not found
        """
        try:
            # Get default WASAPI loopback device
            wasapi_info = self.audio.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = self.audio.get_device_info_by_index(
                wasapi_info["defaultOutputDevice"]
            )

            if not default_speakers["isLoopbackDevice"]:
                # Try to find loopback device
                for loopback in self.audio.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        logger.info(f"Found loopback device: {loopback['name']}")
                        return loopback
            else:
                logger.info(f"Using default loopback: {default_speakers['name']}")
                return default_speakers

            logger.error("No loopback device found")
            return None

        except Exception as e:
            logger.error(f"Error finding loopback device: {e}")
            return None

    def start_recording(self, callback: Optional[Callable] = None, use_microphone: bool = False, microphone_device_index: Optional[int] = None, audio_frame_callback: Optional[Callable] = None):
        """
        Start recording audio from loopback device or microphone.

        Args:
            callback: Optional callback function called when a chunk is ready
            use_microphone: If True, use microphone instead of loopback
            microphone_device_index: Optional specific microphone device index
            audio_frame_callback: Optional callback(audio_data: bytes) for raw audio frames
        """
        if self.recording:
            logger.warning("Recording already in progress")
            return

        if use_microphone:
            # Use specified or default microphone input
            device = self.get_default_microphone(device_index=microphone_device_index)
            if not device:
                raise RuntimeError("Could not find microphone device")
            logger.info(f"Using microphone input: {device['name']}")
        else:
            # Use loopback device
            device = self.get_loopback_device()
            if not device:
                raise RuntimeError("Could not find loopback audio device")
            logger.info("Using system audio loopback")

        self.recording = True
        self.chunk_start_time = time.time()
        self.audio_frame_callback = audio_frame_callback

        # Start capture thread
        self.capture_thread = threading.Thread(
            target=self._capture_loop,
            args=(device, callback, use_microphone),
            daemon=True
        )
        self.capture_thread.start()
        logger.info("Audio recording started")

    def stop_recording(self):
        """Stop recording audio."""
        if not self.recording:
            return

        self.recording = False

        # Stop the stream BEFORE joining the capture thread.
        # stream.read() is a blocking call — if the microphone buffer is slow
        # to fill (quiet room, device stall), it blocks until chunk_size frames
        # arrive. Calling join() first means we wait up to 5 seconds for
        # stream.read() to unblock naturally. If it doesn't, join() times out
        # and _save_chunk() runs while the thread is still appending data,
        # saving only the frames captured AFTER join() returned (~16 frames =
        # 32KB) instead of the full partial chunk (~27 seconds = ~2.5MB).
        # Stopping the stream first causes stream.read() to raise an exception
        # immediately, so the thread exits within ~100ms and join() returns
        # with all buffered data intact.
        if self.stream:
            try:
                self.stream.stop_stream()
            except Exception as e:
                logger.warning(f"Error stopping stream: {e}")

        # Wait for capture thread to exit (fast now that stream is stopped)
        if self.capture_thread:
            self.capture_thread.join(timeout=5)
            if self.capture_thread.is_alive():
                logger.warning("Capture thread still alive after 5s — final chunk may be incomplete")

        # Close stream resources
        if self.stream:
            try:
                self.stream.close()
            except Exception as e:
                logger.warning(f"Error closing stream: {e}")
            self.stream = None

        # Save any remaining audio in buffer
        if self.current_chunk:
            self._save_chunk()

        logger.info("Audio recording stopped")

    def _capture_loop(self, device: dict, callback: Optional[Callable], use_microphone: bool = False):
        """
        Main capture loop running in separate thread.

        Args:
            device: Audio device info
            callback: Optional callback for chunk completion
            use_microphone: Whether using microphone input
        """
        try:
            # Calculate chunk size in frames
            chunk_size = 1024

            # Use optimal settings for microphone
            if use_microphone:
                # Use mono, but keep device's native sample rate
                # (AssemblyAI can handle 16kHz, 44.1kHz, 48kHz, etc.)
                channels = 1 if device["maxInputChannels"] >= 1 else device["maxInputChannels"]
                sample_rate = int(device["defaultSampleRate"])
            else:
                channels = device["maxInputChannels"]
                sample_rate = int(device["defaultSampleRate"])

            # Store stream parameters for saving chunks (CRITICAL: must match device)
            self.stream_channels = channels
            self.stream_sample_rate = sample_rate

            logger.info(f"Detected microphone sample rate: {sample_rate} Hz (native)")
            logger.info(f"Using {channels} channel(s) for recording")

            # Open audio stream with NATIVE sample rate (no resampling)
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,  # CRITICAL: Use native rate, not Config.AUDIO_SAMPLE_RATE
                frames_per_buffer=chunk_size,
                input=True,
                input_device_index=device["index"],
            )

            logger.info(f"✓ Audio stream opened: {sample_rate}Hz, {channels}ch, 16-bit PCM")

            while self.recording:
                try:
                    # Read audio data
                    data = self.stream.read(chunk_size, exception_on_overflow=False)
                    self.current_chunk.append(data)

                    # Call audio frame callback if set (for streaming transcription)
                    if self.audio_frame_callback:
                        try:
                            self.audio_frame_callback(data)
                        except Exception as e:
                            logger.error(f"Error in audio frame callback: {e}")

                    # Check if chunk duration reached
                    elapsed = time.time() - self.chunk_start_time
                    if elapsed >= self.chunk_duration:
                        self._save_chunk()
                        if callback:
                            callback()

                except Exception as e:
                    if not self.recording:
                        # Stream was stopped intentionally — exit cleanly
                        break
                    logger.error(f"Error reading audio: {e}")
                    time.sleep(0.1)

        except Exception as e:
            logger.error(f"Error in capture loop: {e}")
            self.recording = False

    def _save_chunk(self):
        """Save current audio chunk to queue and file."""
        if not self.current_chunk:
            return

        try:
            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = Config.RECORDINGS_DIR / f"chunk_{timestamp}.wav"

            # Ensure directory exists
            Config.RECORDINGS_DIR.mkdir(exist_ok=True)

            # Use stored stream parameters - CRITICAL: MUST match actual recording
            channels = self.stream_channels if self.stream_channels else 1
            sample_rate = self.stream_sample_rate if self.stream_sample_rate else 48000

            if not self.stream_sample_rate:
                logger.warning(f"Using fallback sample rate: {sample_rate}Hz (stream rate not set)")

            # Write WAV file with NATIVE sample rate (no resampling)
            with wave.open(str(filename), 'wb') as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
                wf.setframerate(sample_rate)  # CRITICAL: Must match recording rate
                wf.writeframes(b''.join(self.current_chunk))

            # Add to queue
            chunk_info = {
                'filename': filename,
                'duration': time.time() - self.chunk_start_time,
                'timestamp': datetime.now(),
                'sample_rate': sample_rate,  # Actual sample rate used
                'channels': channels
            }
            self.chunk_queue.put(chunk_info)

            logger.info(f"✓ Saved chunk: {filename.name} | {chunk_info['duration']:.1f}s | {sample_rate}Hz | {channels}ch")

            # Reset for next chunk
            self.current_chunk = []
            self.chunk_start_time = time.time()

        except Exception as e:
            logger.error(f"Error saving chunk: {e}")

    def get_next_chunk(self, timeout: float = None) -> Optional[dict]:
        """
        Get the next audio chunk from the queue.

        Args:
            timeout: Max seconds to wait for chunk (None = block indefinitely)

        Returns:
            Chunk info dict or None if timeout/empty
        """
        try:
            return self.chunk_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def cleanup(self):
        """Cleanup resources."""
        self.stop_recording()
        self.audio.terminate()
        logger.info("Audio capture cleaned up")


def test_audio_capture():
    """Test audio capture functionality."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing audio capture...")
    print("This will record system audio for 10 seconds.")
    print("Play some audio (music, video, etc.) to test.\n")

    capture = AudioCapture(chunk_duration=5)  # 5-second chunks for testing

    try:
        # Test device detection
        device = capture.get_loopback_device()
        if device:
            print(f"✓ Found loopback device: {device['name']}")
            print(f"  Sample rate: {device['defaultSampleRate']}Hz")
            print(f"  Channels: {device['maxInputChannels']}")
        else:
            print("✗ No loopback device found")
            return

        # Start recording
        print("\nStarting recording...")
        capture.start_recording()

        # Record for 10 seconds
        time.sleep(10)

        # Stop recording
        print("Stopping recording...")
        capture.stop_recording()

        # Check chunks
        chunks = []
        while True:
            chunk = capture.get_next_chunk(timeout=0.1)
            if not chunk:
                break
            chunks.append(chunk)

        print(f"\n✓ Captured {len(chunks)} chunks:")
        for i, chunk in enumerate(chunks, 1):
            print(f"  Chunk {i}: {chunk['filename'].name} "
                  f"({chunk['duration']:.1f}s)")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")
    finally:
        capture.cleanup()


if __name__ == '__main__':
    import sys

    # Check for command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == '--list-devices':
        # List all audio devices
        capture = AudioCapture()
        capture.list_audio_devices()
        capture.cleanup()
    else:
        # Run normal test
        test_audio_capture()
