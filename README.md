# Pilot — AI Meeting Assistant

An AI-powered Windows meeting assistant that records microphone audio, transcribes it in real-time, extracts action items, and generates structured HTML summaries — all running locally from your system tray.

## Features

- **Real-time transcription** — AssemblyAI streaming + batch transcription
- **AI analysis** — Claude extracts action items, decisions, and key points per chunk
- **Live notifications** — Windows toast alerts when your name is assigned an action
- **Transcription cleanup** — Haiku pass corrects ASR errors before summarization
- **HTML meeting summaries** — Formatted report with embedded audio playback
- **Footnote confidence markers** — Low-confidence transcript sections flagged cleanly
- **Persistent memory** — Context carries across meetings for status reports
- **System tray interface** — Start/stop with one click, no terminal needed

## Requirements

- Windows 10/11
- Python 3.10+
- [AssemblyAI API key](https://www.assemblyai.com/) (free tier: 100 hours/month)
- [Anthropic API key](https://console.anthropic.com/settings/keys)

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API keys and identity

Copy the example and add your values:

```bash
cp .env.example .env
```

Edit `.env` — minimum required fields:

```env
ASSEMBLYAI_API_KEY=your-key-here
ANTHROPIC_API_KEY=sk-ant-...

# Your identity (used for action item detection)
MY_NAME=Alex
MY_NAME_VARIATIONS=Alex,Al
```

### 3. Configure your domain context (recommended)

Pilot works out of the box, but becomes significantly more useful when it understands your domain. Set these in `.env`:

```env
# Who you work with
MY_MANAGER_NAME=Jordan
MY_COLLEAGUE_NAME=Sam
VENDOR_NAME=AcmeCorp
PRODUCT_NAME=ProjectX

# Your timezone for status reports
USER_TIMEZONE=CT
```

**For domain-specific meetings** (medical, legal, compliance, etc.), set a full custom system prompt:

```env
PILOT_SYSTEM_CONTEXT=You are Pilot, an AI meeting assistant for Alex, a Program Manager.\n\nKEY PEOPLE:\n- Alex: The user. Responsible for compliance, provider training, and vendor relationships.\n- Jordan: Alex's manager. Items Jordan assigns carry extra weight.\n- AcmeCorp: The primary vendor partner.\n\nMEETING FOCUS:\n- Prioritize: action items assigned to Alex, compliance deadlines, vendor commitments\n- Track: decisions, follow-up tasks, regulatory items
```

See `src/config.py.example` for a full annotated reference of every setting.

### 4. Select your microphone (optional)

Auto-detection works for most setups. To use a specific microphone:

```bash
python -m src.audio_capture --list-devices
```

Then add to `config.ini`:

```ini
[Audio]
microphone_device_index = 2
```

### 5. Run

```bash
python -m src.main
```

Pilot appears in your system tray. Right-click → **Start Recording** before your meeting.

## How It Works

```
Microphone audio
      │
      ▼ (30-second chunks)
AssemblyAI batch transcription ──► Stored to disk
      │
      ▼ (simultaneously)
AssemblyAI streaming transcription ──► Live display
      │
      ▼
Claude Haiku — ASR error correction
      │
      ▼
Claude Sonnet — Meeting summary
      │
      ▼
HTML report (action items, decisions, transcript with footnotes)
```

Audio chunks are transcribed as they arrive. When you stop recording, any in-flight chunks finish processing, then a full summary is generated and opened in your browser.

## Output

Summaries are saved to `~/Documents/Pilot/summaries/`:

```
Meeting_Summary_20260218_140000.html   ← opens in browser
complete_recording_20260218_140000.wav ← full audio
snippets/                              ← audio clips per action item
```

The HTML summary includes:
- Key milestones and dates
- Action items with assignee, deadline, confidence
- Decisions
- Items requiring clarification
- Meeting synopsis (2–3 paragraphs)
- Full transcript with low-confidence footnotes

## Configuration Reference

All settings live in `.env` (secrets + identity) or `config.ini` (hardware + behaviour). See `src/config.py.example` for the full annotated reference.

| Setting | Where | Default | Description |
|---------|-------|---------|-------------|
| `ASSEMBLYAI_API_KEY` | `.env` | — | Required |
| `ANTHROPIC_API_KEY` | `.env` | — | Required |
| `MY_NAME` | `.env` | `""` | Your name for action item detection |
| `MY_NAME_VARIATIONS` | `.env` | `""` | Comma-separated ASR spelling variants |
| `MY_MANAGER_NAME` | `.env` | `""` | Manager name for prioritization |
| `PRODUCT_NAME` | `.env` | `""` | Product/program for summary headers |
| `USER_TIMEZONE` | `.env` | `CT` | Timezone abbreviation for reports |
| `PILOT_SYSTEM_CONTEXT` | `.env` | auto | Full custom AI system prompt |
| `AUDIO_CHUNK_DURATION` | `.env` | `30` | Seconds per transcription chunk |
| `microphone_device_index` | `config.ini` | auto | Specific mic device number |

## Troubleshooting

**No audio captured** — Run `python -m src.audio_capture --list-devices` and set `microphone_device_index` in `config.ini`.

**Transcript cuts off** — Normal for very short meetings; the final chunk is always processed. Check logs in `logs/meeting_listener.log` for timing details.

**API key errors** — Verify `.env` exists (copied from `.env.example`) and keys have no extra spaces.

**Notifications not showing** — Check Windows Focus Assist settings; run `python -m src.notifier` to test.

## License

MIT License — free to use, modify, and distribute.
