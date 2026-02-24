"""Transcription module using OpenAI gpt-4o-transcribe API."""

import logging
import time
from pathlib import Path
from typing import Optional, Dict
import openai

from .config import Config
from .rate_limiter import APIRateLimiter

logger = logging.getLogger(__name__)


class Transcriber:
    """Transcribes audio using OpenAI Whisper API."""

    def __init__(self, api_key: Optional[str] = None, max_calls_per_minute: int = 10):
        """
        Initialize transcriber.

        Args:
            api_key: OpenAI API key (default from config)
            max_calls_per_minute: Maximum API calls per minute (default: 10)
        """
        self.api_key = api_key or Config.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API key is required")

        self.client = openai.OpenAI(api_key=self.api_key)

        # API RATE LIMITING - Prevent runaway costs
        self.rate_limiter = APIRateLimiter(
            max_calls_per_minute=max_calls_per_minute,
            circuit_breaker_threshold=5
        )
        logger.info(f"gpt-4o-transcribe initialized (rate limit: {max_calls_per_minute} calls/min)")

    def transcribe_audio(
        self,
        audio_file: Path,
        max_retries: int = 3
    ) -> Optional[Dict]:
        """
        Transcribe audio file using OpenAI Whisper API.

        Args:
            audio_file: Path to audio file (WAV, MP3, M4A, etc. — max 25 MB)
            max_retries: Maximum number of retry attempts

        Returns:
            Dict with transcription data or None if failed:
            {
                'text': str,
                'duration': float,   (API call time in seconds)
                'language': str,
                'confidence': float or None,
                # gpt-4o-transcribe uses response_format='json' which does not
                # include segment logprobs, so confidence is always None.
                # _annotate_transcript_confidence() handles None gracefully.
            }
        """
        if not audio_file.exists():
            logger.error(f"Audio file not found: {audio_file}")
            return None

        for attempt in range(max_retries):
            try:
                can_call, wait_seconds = self.rate_limiter.can_make_call()

                if not can_call:
                    if self.rate_limiter.circuit_open:
                        logger.error(f"Circuit breaker open — cannot make API call. Wait {wait_seconds:.1f}s")
                        if attempt < max_retries - 1:
                            time.sleep(wait_seconds)
                            continue
                        else:
                            logger.error("Circuit breaker prevented all retry attempts")
                            return None
                    else:
                        logger.warning(f"Rate limited — waiting {wait_seconds:.1f}s before retry")
                        time.sleep(wait_seconds)
                        continue

                logger.info(f"Transcribing {audio_file.name} via gpt-4o-transcribe (attempt {attempt + 1}/{max_retries})")
                start_time = time.time()

                with open(audio_file, 'rb') as f:
                    response = self.client.audio.transcriptions.create(
                        model='gpt-4o-transcribe',
                        file=f,
                        response_format='json',
                        language='en',
                        temperature=Config.WHISPER_TEMPERATURE,
                    )

                self.rate_limiter.record_call(success=True)
                elapsed = time.time() - start_time

                # gpt-4o-transcribe returns response_format='json' which has no
                # segment-level logprobs. Confidence remains None; the rest of the
                # pipeline handles None gracefully (no confidence annotation).
                confidence = None

                result = {
                    'text': (response.text or '').strip(),
                    'duration': elapsed,
                    'language': getattr(response, 'language', 'en'),
                    'confidence': confidence,
                }

                result = self._fix_name_transcription_errors(result)

                conf_str = f", confidence={confidence:.2%}" if confidence is not None else ""
                logger.info(f"Transcription done in {elapsed:.1f}s: {len(result['text'])} chars{conf_str}")

                return result

            except openai.RateLimitError as e:
                logger.warning(f"Whisper rate limit (attempt {attempt + 1}): {e}")
                self.rate_limiter.record_call(success=False)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt * 5)
                    continue
                return None

            except Exception as e:
                logger.error(f"Transcription error (attempt {attempt + 1}): {e}")
                self.rate_limiter.record_call(success=False)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    logger.error("Max retries reached, transcription failed")
                    stats = self.rate_limiter.get_stats()
                    logger.info(f"Rate limiter stats: {stats}")
                    return None

        return None

    def transcribe_chunk(self, chunk_info: Dict) -> Optional[Dict]:
        """
        Transcribe an audio chunk from the capture module.

        Args:
            chunk_info: Chunk info dict from AudioCapture

        Returns:
            Dict with transcription and chunk metadata
        """
        result = self.transcribe_audio(chunk_info['filename'])

        if result:
            result.update({
                'chunk_filename': chunk_info['filename'],
                'chunk_duration': chunk_info['duration'],
                'chunk_timestamp': chunk_info['timestamp'],
            })

        return result

    def batch_transcribe(
        self,
        audio_files: list,
        callback=None
    ) -> list:
        """
        Transcribe multiple audio files.

        Args:
            audio_files: List of audio file paths
            callback: Optional callback(result) called after each transcription

        Returns:
            List of transcription results
        """
        results = []

        for i, audio_file in enumerate(audio_files, 1):
            logger.info(f"Transcribing file {i}/{len(audio_files)}: {audio_file.name}")

            result = self.transcribe_audio(audio_file)

            if result:
                result['file_index'] = i
                results.append(result)

                if callback:
                    callback(result)
            else:
                logger.warning(f"Failed to transcribe: {audio_file}")

        return results

    def _fix_name_transcription_errors(self, result: Dict) -> Dict:
        """
        Fix common name transcription errors.

        Args:
            result: Transcription result dict

        Returns:
            Corrected transcription result
        """
        import re

        # Define name corrections (misspelled -> correct).
        # Add entries here if Whisper commonly misspells names in your meetings.
        name_corrections: dict = {}

        for wrong, correct in name_corrections.items():
            result['text'] = re.sub(wrong, correct, result['text'], flags=re.IGNORECASE)

        if 'words' in result:
            for word_dict in result['words']:
                for wrong, correct in name_corrections.items():
                    if re.match(wrong, word_dict['text'], re.IGNORECASE):
                        word_dict['text'] = correct

        if 'utterances' in result:
            for utterance in result['utterances']:
                for wrong, correct in name_corrections.items():
                    utterance['text'] = re.sub(wrong, correct, utterance['text'], flags=re.IGNORECASE)

        return result


def test_transcription():
    """Test transcription functionality."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing transcription module with OpenAI gpt-4o-transcribe...")

    if not Config.OPENAI_API_KEY or Config.OPENAI_API_KEY == 'your-openai-key-here':
        print("✗ Error: OPENAI_API_KEY not set in .env file")
        print("  1. Copy .env.example to .env")
        print("  2. Add your OpenAI API key")
        print("  Get your key at: https://platform.openai.com/api-keys")
        return

    try:
        transcriber = Transcriber()
        print("✓ Transcriber initialized")

        recordings_dir = Config.RECORDINGS_DIR
        if not recordings_dir.exists():
            print(f"\n✗ No recordings directory found: {recordings_dir}")
            print("  Run audio_capture.py first to create test recordings")
            return

        audio_files = list(recordings_dir.glob("*.wav"))
        if not audio_files:
            print(f"\n✗ No audio files found in {recordings_dir}")
            print("  Run audio_capture.py first to create test recordings")
            return

        print(f"\n✓ Found {len(audio_files)} audio file(s)")

        test_file = audio_files[0]
        print(f"\nTranscribing: {test_file.name}")

        result = transcriber.transcribe_audio(test_file)

        if result:
            print("\n✓ Transcription successful!")
            print(f"  Language: {result['language']}")
            print(f"  Duration: {result['duration']:.1f}s")
            if result.get('confidence') is not None:
                print(f"  Confidence: {result['confidence']:.2%}")
            print(f"  Text length: {len(result['text'])} characters")
            print(f"\nTranscription:\n{'-' * 60}")
            print(result['text'])
            print('-' * 60)
        else:
            print("\n✗ Transcription failed")

    except Exception as e:
        print(f"\n✗ Error: {e}")


if __name__ == '__main__':
    test_transcription()
