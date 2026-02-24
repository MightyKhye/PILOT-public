"""Fix existing recordings with wrong channel count (stereo->mono)."""

import wave
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_recording(wav_path: Path):
    """Fix a WAV file with wrong channel count."""
    try:
        # Read original file
        with wave.open(str(wav_path), 'rb') as original:
            params = original.getparams()
            frames = original.readframes(params.nframes)

            channels = params.nchannels
            sample_rate = params.framerate
            sample_width = params.sampwidth

            logger.info(f"Original: {wav_path.name} - {channels} channels, {sample_rate}Hz")

            # Only fix if it's stereo but should be mono
            if channels != 2:
                logger.info(f"  Skipping (already {channels} channel(s))")
                return False

        # Create backup
        backup_path = wav_path.with_suffix('.wav.backup')
        if not backup_path.exists():
            wav_path.rename(backup_path)
            logger.info(f"  Created backup: {backup_path.name}")
        else:
            # Backup already exists, read from it
            with wave.open(str(backup_path), 'rb') as original:
                params = original.getparams()
                frames = original.readframes(params.nframes)

        # Write corrected file (mono, same sample rate)
        with wave.open(str(wav_path), 'wb') as fixed:
            fixed.setnchannels(1)  # Mono
            fixed.setsampwidth(sample_width)
            fixed.setframerate(sample_rate)
            fixed.writeframes(frames)

        logger.info(f"  ✓ Fixed: Now 1 channel (mono), {sample_rate}Hz")
        return True

    except Exception as e:
        logger.error(f"  ✗ Error fixing {wav_path.name}: {e}")
        return False


def main():
    """Fix all recordings in meetings directory."""
    meetings_dir = Path.home() / "Documents" / "Pilot" / "summaries"

    # Find all complete recordings
    recordings = list(meetings_dir.glob("complete_recording_*.wav"))

    if not recordings:
        logger.warning("No recordings found to fix")
        return

    logger.info(f"Found {len(recordings)} recordings to check/fix\n")

    fixed_count = 0
    for recording in recordings:
        if fix_recording(recording):
            fixed_count += 1
        print()

    logger.info(f"\nDone! Fixed {fixed_count} recordings")
    logger.info(f"Originals backed up as *.wav.backup")


if __name__ == '__main__':
    main()
