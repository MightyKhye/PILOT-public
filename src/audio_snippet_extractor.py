"""Audio snippet extraction for action items."""

import wave
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class AudioSnippetExtractor:
    """Extract and save audio snippets for action items."""

    def __init__(self, recordings_dir: Path, snippets_dir: Path):
        """
        Initialize the audio snippet extractor.

        Args:
            recordings_dir: Directory containing audio chunk files
            snippets_dir: Directory to save audio snippets
        """
        self.recordings_dir = Path(recordings_dir)
        self.snippets_dir = Path(snippets_dir)
        self.snippets_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"AudioSnippetExtractor initialized (snippets: {self.snippets_dir})")

    def extract_snippet_for_action_item(
        self,
        action_item: dict,
        transcription: dict,
        before_duration: float = 10.0,
        after_duration: float = 5.0
    ) -> Optional[Path]:
        """
        Extract audio snippet for an action item.

        Args:
            action_item: Dict with 'item', 'assignee', 'deadline', 'confidence'
            transcription: Full transcription with 'text', 'words[]', 'chunk_filename', etc.
            before_duration: Seconds to include before action item
            after_duration: Seconds to include after action item

        Returns:
            Path to saved snippet WAV file, or None if extraction failed
        """
        try:
            item_text = action_item.get('item', '')
            if not item_text:
                logger.warning("Action item has no text, skipping snippet extraction")
                return None

            # Get transcription data
            words = transcription.get('words', [])
            chunk_filename = transcription.get('chunk_filename')
            chunk_timestamp = transcription.get('chunk_timestamp')
            sample_rate = transcription.get('sample_rate', 16000)
            channels = transcription.get('channels', 1)

            if not words or not chunk_filename:
                logger.warning("Transcription missing words or chunk_filename")
                return None

            # Find action item location in transcription
            start_time, end_time = self._find_action_item_in_transcription(item_text, words)
            if start_time is None or end_time is None:
                logger.warning(f"Could not find action item in transcription: {item_text[:50]}")
                return None

            logger.info(f"Found action item at {start_time:.2f}s - {end_time:.2f}s")

            # Expand to include context
            snippet_start = max(0, start_time - before_duration)
            snippet_end = end_time + after_duration

            # Extract audio segment
            audio_data = self._extract_audio_segment(
                chunk_file=Path(chunk_filename),
                start_time=snippet_start,
                end_time=snippet_end,
                sample_rate=sample_rate,
                channels=channels
            )

            if not audio_data:
                logger.warning("Failed to extract audio segment")
                return None

            # Save snippet
            snippet_path = self._save_snippet(
                audio_data=audio_data,
                action_item=action_item,
                timestamp=chunk_timestamp,
                sample_rate=sample_rate,
                channels=channels
            )

            logger.info(f"Saved snippet: {snippet_path.name}")
            return snippet_path

        except Exception as e:
            logger.error(f"Error extracting snippet: {e}", exc_info=True)
            return None

    def _find_action_item_in_transcription(
        self,
        action_item_text: str,
        transcription_words: List[dict]
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Find start/end timestamps for action item text in transcription.

        Uses fuzzy matching to locate the relevant words.

        Args:
            action_item_text: The action item description
            transcription_words: List of word dicts with 'text', 'start', 'end'

        Returns:
            (start_time, end_time) in seconds, or (None, None) if not found
        """
        if not transcription_words:
            return None, None

        # Normalize action item text
        action_normalized = self._normalize_text(action_item_text)
        action_words = action_normalized.split()

        if not action_words:
            return None, None

        # Build full transcription text with word indices
        full_text = ' '.join(w.get('text', '') for w in transcription_words)
        full_text_normalized = self._normalize_text(full_text)

        # Try exact substring match first
        if action_normalized in full_text_normalized:
            # Find which words match
            matched_indices = self._find_word_indices_for_substring(
                action_normalized,
                transcription_words
            )
            if matched_indices:
                start_idx, end_idx = matched_indices
                return (
                    transcription_words[start_idx]['start'],
                    transcription_words[end_idx]['end']
                )

        # Fall back to fuzzy matching with sliding window
        best_match_ratio = 0.0
        best_match_start = None
        best_match_end = None

        # Use sliding window approach
        window_size = min(len(action_words) + 10, len(transcription_words))

        for i in range(len(transcription_words) - len(action_words) + 1):
            window_end = min(i + window_size, len(transcription_words))
            window_words = transcription_words[i:window_end]
            window_text = ' '.join(w.get('text', '') for w in window_words)
            window_normalized = self._normalize_text(window_text)

            # Calculate similarity ratio
            ratio = SequenceMatcher(None, action_normalized, window_normalized).ratio()

            if ratio > best_match_ratio:
                best_match_ratio = ratio
                best_match_start = i
                best_match_end = window_end - 1

        # Accept match if ratio is above threshold
        if best_match_ratio >= 0.45 and best_match_start is not None:
            logger.info(f"Fuzzy match found (ratio={best_match_ratio:.2f})")
            return (
                transcription_words[best_match_start]['start'],
                transcription_words[best_match_end]['end']
            )

        logger.warning(f"No good match found (best ratio={best_match_ratio:.2f})")
        return None, None

    def _find_word_indices_for_substring(
        self,
        substring: str,
        words: List[dict]
    ) -> Optional[Tuple[int, int]]:
        """
        Find start and end word indices for a substring in the transcription.

        Args:
            substring: Normalized substring to find
            words: List of word dicts

        Returns:
            (start_index, end_index) or None if not found
        """
        full_text = ' '.join(w.get('text', '') for w in words)
        full_text_normalized = self._normalize_text(full_text)

        char_start = full_text_normalized.find(substring)
        if char_start == -1:
            return None

        char_end = char_start + len(substring)

        # Map character positions to word indices
        current_pos = 0
        start_idx = None
        end_idx = None

        for i, word in enumerate(words):
            word_text = self._normalize_text(word.get('text', ''))
            word_start = current_pos
            word_end = current_pos + len(word_text)

            if start_idx is None and word_end > char_start:
                start_idx = i

            if word_start < char_end:
                end_idx = i

            current_pos = word_end + 1  # +1 for space

        if start_idx is not None and end_idx is not None:
            return start_idx, end_idx

        return None

    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching (lowercase, remove punctuation)."""
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)  # Remove punctuation
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        return text.strip()

    def _extract_audio_segment(
        self,
        chunk_file: Path,
        start_time: float,
        end_time: float,
        sample_rate: int,
        channels: int
    ) -> Optional[bytes]:
        """
        Extract audio segment from WAV file.

        Args:
            chunk_file: Path to source WAV file
            start_time: Start position in seconds
            end_time: End position in seconds
            sample_rate: Audio sample rate
            channels: Number of audio channels

        Returns:
            Raw audio bytes, or None if extraction failed
        """
        try:
            if not chunk_file.exists():
                logger.error(f"Chunk file not found: {chunk_file}")
                return None

            with wave.open(str(chunk_file), 'rb') as wav:
                # Verify parameters
                wav_sample_rate = wav.getframerate()
                wav_channels = wav.getnchannels()
                sample_width = wav.getsampwidth()

                # Calculate frame positions
                start_frame = int(start_time * wav_sample_rate)
                end_frame = int(end_time * wav_sample_rate)
                num_frames = end_frame - start_frame

                if num_frames <= 0:
                    logger.warning(f"Invalid frame range: {start_frame} to {end_frame}")
                    return None

                # Seek to start position
                wav.setpos(start_frame)

                # Read frames
                audio_data = wav.readframes(num_frames)

                logger.debug(f"Extracted {num_frames} frames from {chunk_file.name}")
                return audio_data

        except Exception as e:
            logger.error(f"Error reading WAV file {chunk_file}: {e}")
            return None

    def _save_snippet(
        self,
        audio_data: bytes,
        action_item: dict,
        timestamp: datetime,
        sample_rate: int,
        channels: int
    ) -> Path:
        """
        Save audio snippet with meaningful filename.

        Filename format: snippet_YYYYMMDD_HHMMSS_<sanitized_action_text[:30]>.wav

        Args:
            audio_data: Raw audio bytes
            action_item: Action item dict
            timestamp: Timestamp for filename
            sample_rate: Audio sample rate
            channels: Number of channels

        Returns:
            Path to saved snippet file
        """
        # Create filename
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")[:19]  # Include microseconds
        action_text = action_item.get('item', 'action')
        sanitized_text = self._sanitize_filename(action_text)[:30]
        filename = f"snippet_{timestamp_str}_{sanitized_text}.wav"
        filepath = self.snippets_dir / filename

        # Ensure unique filename
        counter = 1
        while filepath.exists():
            filename = f"snippet_{timestamp_str}_{sanitized_text}_{counter}.wav"
            filepath = self.snippets_dir / filename
            counter += 1

        # Write WAV file
        with wave.open(str(filepath), 'wb') as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)  # 16-bit audio (2 bytes)
            wav.setframerate(sample_rate)
            wav.writeframes(audio_data)

        return filepath

    def _sanitize_filename(self, text: str) -> str:
        """Sanitize text for use in filename."""
        # Remove or replace invalid characters
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '_', text)
        return text.strip('_')
