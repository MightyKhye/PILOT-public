"""Streaming transcription — not available with Whisper backend.

OpenAI Whisper is a batch API and does not support real-time streaming.
This stub keeps the module importable so meeting_manager.py can attempt
to instantiate it; the NotImplementedError is caught and streaming is
gracefully disabled. All recordings use 30-second batch chunks instead.
"""


class StreamingTranscriber:
    """No-op stub — Whisper does not support real-time audio streaming."""

    is_streaming = False
    current_transcript = ""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "Real-time streaming is not supported with the Whisper backend. "
            "Pilot uses 30-second batch chunks for both live recording and uploads."
        )

    def start_streaming(self, *args, **kwargs):
        pass

    def stream_audio(self, *args, **kwargs):
        pass

    def stop_streaming(self):
        pass

    def get_current_transcript(self) -> str:
        return ""
