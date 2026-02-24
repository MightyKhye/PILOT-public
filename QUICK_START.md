# Pilot — AI Meeting Assistant Quick Start

## Features

### Core Features
- **Real-time Audio Capture**: Records ambient audio from your microphone
- **Automatic Transcription**: Uses OpenAI Whisper to transcribe speech
- **AI Analysis**: Claude identifies action items, decisions, and key points
- **Windows Notifications**: Get instant alerts for important items
- **Confidence Tracking**: Shows transcript quality and flags unclear sections

### Enhanced Features
- **Persistent Memory**: Remembers all previous meetings
- **Contextual Learning**: Builds on past meetings for better understanding
- **Live Query**: Ask questions about current or past meetings anytime
- **Document Upload**: Add supporting documents to your knowledge base
- **System Tray Interface**: One-click access from your system tray

## Setup

See `README.md` for full setup instructions. Minimum required:

1. Copy `.env.example` to `.env` and add your API keys
2. Set `MY_NAME` in `.env` (used for action item detection)
3. Run: `python -m src.main`

## How to Use

### Basic Meeting Recording

1. **Launch the app** — `python -m src.main`
2. **Right-click the system tray icon** → Start Recording
3. **Have your meeting** — the app captures audio in 30-second chunks
4. **Stop recording** → system tray → Stop Recording
5. **Find your summary** — opens automatically in your browser

### Query Past Meetings

Use the query feature from the tray menu to ask questions like:
- "What training requirements were discussed in past meetings?"
- "What are the pending action items from last week?"
- "What decisions were made about the vendor timeline?"

Claude searches all meeting history and uploaded documents to answer.

### Upload Documents

1. Select **Upload Document** from the tray menu
2. Enter the full path to your document
   - Example: `C:\Users\YourName\Documents\YourDocument.pdf`
3. The document is saved and used for future queries

### View History

- **Documents**: See all uploaded documents
- **Meetings**: View summaries of past meetings

## Output Files

All files are saved to `~/Documents/Pilot/`:

- **summaries/**: HTML meeting summaries (open in browser)
- **recordings/**: Full audio recordings
- **snippets/**: Audio clips per action item

## Understanding the Output

### Meeting Summary Format

```
MEETING SUMMARY
Date: 2026-02-18 14:00
Transcription Quality: 88%

ACTION ITEMS
- [ ] Alex: Send follow-up email to vendor (Due: Friday) - Confidence: high

DECISIONS
- Approved virtual training for remote sites (Confidence: high)

ITEMS REQUIRING CLARIFICATION
- Specific timeline for provider authorization

MEETING SYNOPSIS
[Professional summary of key discussion points]

COMPLETE TRANSCRIPT
[Full transcript]

---
Transcript Notes:
[1] Low confidence (45%) — "some unclear phrase" may be inaccurate
```

### Confidence Markers

High-confidence text appears as-is. Low-confidence passages are marked with footnote numbers in the transcript body (e.g., `text[1]`) and explained in a **Transcript Notes** section at the bottom.

## Tips

1. **Speak clearly** near the microphone for best transcription
2. **Let it run** — the app processes in 30-second chunks automatically
3. **Use queries** — ask questions to find information across all past meetings
4. **Upload documents** — add domain reference material for better AI context
5. **Check quality** — if overall quality is below 70%, audio may be too quiet

## Troubleshooting

### No audio captured
- Run `python -m src.audio_capture --list-devices` to list available devices
- Set `microphone_device_index` in `config.ini` if auto-detection picks the wrong mic
- Verify Windows microphone permissions

### Low transcription quality
- Reduce background noise
- Move closer to speakers/microphone
- Check that audio is audible when played back

### Query not finding information
- Make sure recording was completed before querying
- Upload relevant documents for better context
- Try rephrasing your question

### Notifications not showing
- Check Windows Focus Assist settings
- Run `python -m src.notifier` to test notifications directly

## Support

For issues, check:
- `logs/` folder for error messages
- Verify API keys are set correctly in `.env`
- See the Troubleshooting section in `README.md`
