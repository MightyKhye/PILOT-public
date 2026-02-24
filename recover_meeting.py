"""Recover and process failed meeting from audio chunks."""
import sys
from pathlib import Path
from datetime import datetime
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.transcription import Transcriber
from src.ai_analyzer import MeetingAnalyzer
from src.config import Config

def recover_meeting(start_time: str, end_time: str):
    """
    Recover a meeting from saved audio chunks.

    Args:
        start_time: Start time in format YYYYMMDD_HHMMSS (e.g., "20260205_203900")
        end_time: End time in format YYYYMMDD_HHMMSS
    """
    print("=" * 70)
    print("MEETING RECOVERY TOOL")
    print("=" * 70)
    print(f"Processing chunks from {start_time} to {end_time}")
    print()

    # Find all chunks in time range
    recordings_dir = Config.RECORDINGS_DIR
    all_chunks = sorted(recordings_dir.glob("chunk_*.wav"))

    # Filter by time range
    target_chunks = []
    for chunk in all_chunks:
        chunk_time = chunk.stem.replace("chunk_", "")
        if start_time <= chunk_time <= end_time:
            target_chunks.append(chunk)

    if not target_chunks:
        print(f"[ERROR] No chunks found in time range {start_time} to {end_time}")
        return None

    print(f"Found {len(target_chunks)} audio chunks to process")
    print()

    # Initialize components
    transcriber = Transcriber()
    analyzer = MeetingAnalyzer()

    transcriptions = []
    analyses = []

    # Process each chunk
    for idx, chunk_path in enumerate(target_chunks, 1):
        percentage = int((idx / len(target_chunks)) * 100)
        print(f"[{idx}/{len(target_chunks)}] ({percentage}%) Processing: {chunk_path.name}")

        try:
            # Transcribe
            print(f"  > Transcribing...")
            chunk_info = {
                'filename': chunk_path,
                'duration': 30,  # 30-second chunks
                'timestamp': datetime.now()
            }
            transcription = transcriber.transcribe_chunk(chunk_info)

            if transcription and transcription.get('text'):
                transcriptions.append(transcription)
                print(f"  + Transcribed: {len(transcription['text'])} characters")

                # Analyze
                print(f"  > Analyzing...")
                analysis = analyzer.analyze_chunk(transcription['text'])

                if analysis:
                    analyses.append({
                        'timestamp': datetime.now(),
                        'analysis': analysis
                    })
                    action_count = len(analysis.get('action_items', []))
                    decision_count = len(analysis.get('decisions', []))
                    print(f"  + Analyzed: {action_count} action items, {decision_count} decisions")
                else:
                    print(f"  ! Analysis failed")
            else:
                print(f"  ! Transcription empty or failed")

        except Exception as e:
            print(f"  X Error: {e}")

        print()

    # Generate summary
    print("=" * 70)
    print("GENERATING MEETING SUMMARY")
    print("=" * 70)

    if not transcriptions:
        print("[ERROR] No transcriptions to summarize")
        return None

    # Calculate average confidence
    avg_confidence = 0.0
    confidences = [t.get('confidence', 0) for t in transcriptions if t.get('confidence')]
    if confidences:
        avg_confidence = sum(confidences) / len(confidences)

    # Collect word-level confidence data
    all_words = []
    for transcription in transcriptions:
        if 'words' in transcription and transcription['words']:
            all_words.append(transcription['words'])

    # Generate summary
    summary = analyzer.generate_summary(
        transcription_confidence=avg_confidence,
        transcription_words=all_words if all_words else None
    )

    # Save everything
    meeting_id = start_time
    meeting_start = datetime.strptime(start_time, "%Y%m%d_%H%M%S")

    # Save summary
    summary_filename = f"meeting_{meeting_id}_recovered.md"
    summary_path = Config.MEETINGS_DIR / summary_filename

    metadata = f"""Business MEETING SUMMARY (RECOVERED)
Date: {meeting_start.strftime('%Y-%m-%d %H:%M')}
Transcription Quality: {avg_confidence:.1%}
Chunks Processed: {len(transcriptions)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""

    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(metadata + summary)

    # Save JSON data
    data_path = Config.MEETINGS_DIR / f"meeting_{meeting_id}_recovered.json"
    duration_minutes = len(target_chunks) * 0.5  # 30-second chunks
    meeting_data = {
        'meeting_id': meeting_id + '_recovered',
        'start_time': meeting_start.isoformat(),
        'duration': f"{int(duration_minutes)}m",
        'transcriptions': [
            {
                'text': t['text'],
                'timestamp': t['chunk_timestamp'].isoformat() if 'chunk_timestamp' in t else str(t.get('timestamp', ''))
            }
            for t in transcriptions
        ],
        'analyses': [
            {
                'timestamp': a['timestamp'].isoformat(),
                'analysis': a['analysis']
            }
            for a in analyses
        ]
    }

    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(meeting_data, f, indent=2)

    # Copy to Downloads
    try:
        import shutil
        downloads_path = Path.home() / 'Downloads' / f"Meeting_Summary_{meeting_id}_RECOVERED.md"
        shutil.copy(summary_path, downloads_path)
        print(f"+ Copied to Downloads: {downloads_path}")
    except Exception as e:
        print(f"! Could not copy to Downloads: {e}")

    print()
    print("=" * 70)
    print("RECOVERY COMPLETE")
    print("=" * 70)
    print(f"Summary: {summary_path}")
    print(f"Data: {data_path}")
    print(f"Transcriptions: {len(transcriptions)}")
    print(f"Analyses: {len(analyses)}")
    print(f"Duration: ~{int(duration_minutes)} minutes")
    print("=" * 70)

    return summary_path


if __name__ == '__main__':
    print()
    print("This will recover the failed meeting from 8:39 PM - 9:22 PM")
    print("Processing will take several minutes (transcription + AI analysis)")
    print()

    confirm = input("Continue? (y/n): ").strip().lower()
    if confirm == 'y':
        # Recover meeting from 8:39 PM to 9:22 PM
        result = recover_meeting("20260205_203900", "20260205_212300")

        if result:
            print("\n[OK] Meeting successfully recovered!")
            print(f"Check your Downloads folder for the summary.")
        else:
            print("\n[ERROR] Recovery failed")
    else:
        print("Cancelled")
