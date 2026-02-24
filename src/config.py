"""Configuration management for Meeting Listener app."""

import os
import configparser
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


def _build_default_system_context() -> str:
    """
    Build a generic Pilot system context from .env variables.

    To fully customize, set PILOT_SYSTEM_CONTEXT in .env as a single string.
    To use the generated default, set individual vars:
      MY_NAME, MY_MANAGER_NAME, MY_COLLEAGUE_NAME, VENDOR_NAME, PRODUCT_NAME
    """
    name = os.getenv('MY_NAME', '')
    manager = os.getenv('MY_MANAGER_NAME', '')
    colleague = os.getenv('MY_COLLEAGUE_NAME', '')
    vendor = os.getenv('VENDOR_NAME', '')
    product = os.getenv('PRODUCT_NAME', '')
    user_ref = name or "the user"

    people_lines = []
    if name:
        people_lines.append(f"- {name}: The user you assist.")
    if manager:
        people_lines.append(
            f"- {manager}: {user_ref}'s direct manager. "
            f"Items assigned to or approved by {manager} carry extra weight."
        )
    if colleague:
        people_lines.append(f"- {colleague}: {user_ref}'s colleague.")
    if vendor:
        people_lines.append(f"- {vendor}: A key vendor or partner.")

    parts = [f"You are Pilot, an AI meeting assistant{f' for {name}' if name else ''}."]
    if people_lines:
        parts.append("\nKEY PEOPLE:\n" + "\n".join(people_lines))
    if product:
        parts.append(f"\nPRODUCT CONTEXT:\n- {product} is the primary product or program being discussed.")
    parts.append(
        f"\nMEETING FOCUS:\n"
        f"- Prioritize: action items assigned to {user_ref}, commitments made by others, "
        f"and any compliance or time-sensitive items\n"
        f"- Track: deadlines, decisions, and follow-up tasks\n"
        f"- When summarizing, highlight items most relevant to {user_ref}"
    )
    return "\n".join(parts)


class Config:
    """Application configuration."""

    # API Keys (from .env only - NEVER commit these)
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')       # Whisper transcription
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')  # Claude analysis

    # Audio Configuration
    AUDIO_CHUNK_DURATION = int(os.getenv('AUDIO_CHUNK_DURATION', '30'))  # seconds
    # NOTE: Sample rate is AUTO-DETECTED from the microphone device (usually 48000 Hz)
    # Whisper handles all sample rates natively — no manual configuration needed.
    AUDIO_FORMAT = 'paInt16'  # 16-bit audio

    # temperature=0 → deterministic output (no sampling noise)
    WHISPER_TEMPERATURE = float(os.getenv('WHISPER_TEMPERATURE', '0'))

    # Paths - PORTABLE (no hard-coded usernames)
    BASE_DIR = Path(__file__).parent.parent

    # Use user's Documents folder for meeting data (cross-platform safe)
    if os.name == 'nt':  # Windows
        USER_DOCS_DIR = Path(os.path.expanduser("~")) / "Documents" / "Pilot"
    else:  # macOS/Linux
        USER_DOCS_DIR = Path(os.path.expanduser("~")) / "Documents" / "Pilot"

    # Recordings stay in project folder (temporary files)
    RECORDINGS_DIR = BASE_DIR / 'recordings'

    # Meetings data in user's Documents (permanent storage)
    MEETINGS_DIR = USER_DOCS_DIR / 'meetings'
    SUMMARIES_DIR = USER_DOCS_DIR / 'summaries'

    # Logs in project folder
    LOGS_DIR = BASE_DIR / 'logs'

    # Snippets with meetings data
    SNIPPETS_DIR = MEETINGS_DIR / 'snippets'

    # Failed chunks persistence
    FAILED_CHUNKS_DIR = BASE_DIR / 'failed_chunks'

    # Audio Snippet Configuration
    SNIPPET_BEFORE_DURATION = float(os.getenv('SNIPPET_BEFORE_DURATION', '10.0'))
    SNIPPET_AFTER_DURATION = float(os.getenv('SNIPPET_AFTER_DURATION', '5.0'))
    SNIPPET_ENABLED = os.getenv('SNIPPET_ENABLED', 'true').lower() == 'true'

    # Recording Indicator Configuration
    INDICATOR_ENABLED = os.getenv('INDICATOR_ENABLED', 'true').lower() == 'true'
    INDICATOR_SHOW_TIME = os.getenv('INDICATOR_SHOW_TIME', 'true').lower() == 'true'
    INDICATOR_SHOW_CHUNKS = os.getenv('INDICATOR_SHOW_CHUNKS', 'true').lower() == 'true'

    # Live Action Item Notifications
    LIVE_ACTION_NOTIFICATIONS = os.getenv('LIVE_ACTION_NOTIFICATIONS', 'true').lower() == 'true'
    NOTIFICATION_DURATION = int(os.getenv('NOTIFICATION_DURATION', '5'))
    AUTO_APPROVE_TIMEOUT = int(os.getenv('AUTO_APPROVE_TIMEOUT', '5'))
    PLAY_NOTIFICATION_SOUND = os.getenv('PLAY_NOTIFICATION_SOUND', 'false').lower() == 'true'

    # User identity — used for name detection in live transcripts and AI prompts.
    # Set these in .env to customize for your name and team.
    MY_NAME = os.getenv('MY_NAME', '')
    MY_NAME_VARIATIONS = [v.strip() for v in os.getenv('MY_NAME_VARIATIONS', '').split(',') if v.strip()]
    MY_MANAGER_NAME = os.getenv('MY_MANAGER_NAME', '')
    MY_COLLEAGUE_NAME = os.getenv('MY_COLLEAGUE_NAME', '')
    VENDOR_NAME = os.getenv('VENDOR_NAME', '')
    PRODUCT_NAME = os.getenv('PRODUCT_NAME', '')

    # Timezone used for status report date/time formatting (e.g. "CT", "ET", "PT")
    USER_TIMEZONE = os.getenv('USER_TIMEZONE', 'CT')

    # Pilot AI context — injected into all AI prompts as the system message.
    # Option A (recommended): Set PILOT_SYSTEM_CONTEXT in .env as a full custom string.
    # Option B: Set MY_NAME / MY_MANAGER_NAME / MY_COLLEAGUE_NAME / VENDOR_NAME /
    #           PRODUCT_NAME in .env and a context is generated automatically.
    PILOT_SYSTEM_CONTEXT = os.getenv('PILOT_SYSTEM_CONTEXT', '') or _build_default_system_context()

    # Microphone Configuration (from config.ini or auto-detect)
    MICROPHONE_DEVICE_INDEX = None  # None = auto-detect, or specific index
    AUTO_CLEANUP_RECORDINGS = True
    SUMMARY_AUTO_OPEN = True
    LIVE_ACTION_NOTIFICATIONS_ENABLED = True  # Can be toggled at runtime

    # Config file for user settings (NOT API keys)
    CONFIG_FILE = BASE_DIR / 'config.ini'

    @classmethod
    def load_user_config(cls):
        """Load user settings from config.ini if it exists."""
        if not cls.CONFIG_FILE.exists():
            cls._create_default_config()
            return

        try:
            config = configparser.ConfigParser()
            config.read(cls.CONFIG_FILE)

            # Load audio settings
            if 'Audio' in config:
                if 'microphone_device_index' in config['Audio']:
                    value = config['Audio']['microphone_device_index']
                    cls.MICROPHONE_DEVICE_INDEX = int(value) if value.lower() != 'none' else None

            # Load path settings
            if 'Paths' in config:
                if 'summary_output_path' in config['Paths']:
                    custom_path = config['Paths']['summary_output_path']
                    if custom_path and custom_path.lower() != 'default':
                        cls.SUMMARIES_DIR = Path(custom_path)

            # Load behavior settings
            if 'Behavior' in config:
                if 'auto_cleanup_recordings' in config['Behavior']:
                    cls.AUTO_CLEANUP_RECORDINGS = config['Behavior'].getboolean('auto_cleanup_recordings', True)
                if 'summary_auto_open' in config['Behavior']:
                    cls.SUMMARY_AUTO_OPEN = config['Behavior'].getboolean('summary_auto_open', True)

            # Load notification settings
            if 'Notifications' in config:
                if 'live_action_items' in config['Notifications']:
                    cls.LIVE_ACTION_NOTIFICATIONS = config['Notifications'].getboolean('live_action_items', True)
                if 'notification_duration' in config['Notifications']:
                    cls.NOTIFICATION_DURATION = config['Notifications'].getint('notification_duration', 5)
                if 'auto_approve_timeout' in config['Notifications']:
                    cls.AUTO_APPROVE_TIMEOUT = config['Notifications'].getint('auto_approve_timeout', 5)
                if 'play_notification_sound' in config['Notifications']:
                    cls.PLAY_NOTIFICATION_SOUND = config['Notifications'].getboolean('play_notification_sound', False)
                if 'my_name' in config['Notifications']:
                    cls.MY_NAME = config['Notifications']['my_name']
                if 'my_name_variations' in config['Notifications']:
                    cls.MY_NAME_VARIATIONS = [v.strip() for v in config['Notifications']['my_name_variations'].split(',')]

            print(f"Loaded user config from {cls.CONFIG_FILE}")

        except Exception as e:
            print(f"Warning: Could not load config.ini: {e}")
            print("Using default settings")

    @classmethod
    def _create_default_config(cls):
        """Create default config.ini with comments."""
        config = configparser.ConfigParser()

        config['Audio'] = {
            '# Microphone device index (None for auto-detect, or specific number)': '',
            'microphone_device_index': 'None',
            '# Run: python -m src.audio_capture --list-devices to see available devices': ''
        }

        config['Paths'] = {
            '# Where to save meeting summaries (default uses Documents/Pilot/summaries)': '',
            'summary_output_path': 'default'
        }

        config['Behavior'] = {
            '# Automatically delete old recording chunks after processing': '',
            'auto_cleanup_recordings': 'true',
            '# Automatically open summary in browser when meeting ends': '',
            'summary_auto_open': 'true'
        }

        config['Notifications'] = {
            '# Show real-time notifications for action items during meetings': '',
            'live_action_items': 'true',
            '# How long to show notification (seconds)': '',
            'notification_duration': '5',
            '# Auto-approve timeout (seconds)': '',
            'auto_approve_timeout': '5',
            '# Play sound when notification appears': '',
            'play_notification_sound': 'false',
            '# Your name (for detection in transcripts)': '',
            'my_name': '',
            '# Name variations (comma-separated, in case transcription gets it wrong)': '',
            'my_name_variations': ''
        }

        try:
            with open(cls.CONFIG_FILE, 'w') as f:
                config.write(f)
            print(f"Created default config.ini at {cls.CONFIG_FILE}")
        except Exception as e:
            print(f"Warning: Could not create config.ini: {e}")

    @classmethod
    def validate(cls):
        """Validate configuration and API keys."""
        errors = []

        if not cls.OPENAI_API_KEY or cls.OPENAI_API_KEY == 'your-openai-key-here':
            errors.append("Missing or invalid OPENAI_API_KEY in .env file")

        if not cls.ANTHROPIC_API_KEY or cls.ANTHROPIC_API_KEY == 'sk-ant-...':
            errors.append("Missing or invalid ANTHROPIC_API_KEY in .env file")

        if cls.AUDIO_CHUNK_DURATION < 5 or cls.AUDIO_CHUNK_DURATION > 300:
            errors.append(f"AUDIO_CHUNK_DURATION must be between 5 and 300 seconds (got {cls.AUDIO_CHUNK_DURATION})")

        return errors

    @classmethod
    def create_directories(cls):
        """Create necessary directories if they don't exist."""
        cls.RECORDINGS_DIR.mkdir(exist_ok=True, parents=True)
        cls.MEETINGS_DIR.mkdir(exist_ok=True, parents=True)
        cls.SUMMARIES_DIR.mkdir(exist_ok=True, parents=True)
        cls.LOGS_DIR.mkdir(exist_ok=True, parents=True)
        cls.SNIPPETS_DIR.mkdir(exist_ok=True, parents=True)
        cls.FAILED_CHUNKS_DIR.mkdir(exist_ok=True, parents=True)
        cls.USER_DOCS_DIR.mkdir(exist_ok=True, parents=True)


def _ensure_ffmpeg_on_path():
    """
    Auto-detect ffmpeg and add it to PATH if not already accessible.

    Called at module load so pydub audio conversions (M4A, MP3, etc.) work
    without requiring users to manually configure PATH.
    Only affects M4A/MP3 uploads — WAV files and live recording are unaffected.
    """
    import shutil
    if shutil.which('ffmpeg'):
        return  # Already on PATH — nothing to do

    common_paths = [
        r'C:\ProgramData\chocolatey\bin',              # choco install ffmpeg
        r'C:\ffmpeg\bin',                               # manual extract to C:\ffmpeg
        r'C:\Program Files\ffmpeg\bin',                 # installer
        r'C:\Program Files (x86)\ffmpeg\bin',
        r'C:\tools\ffmpeg\bin',                         # scoop or manual
        str(Path.home() / 'ffmpeg' / 'bin'),            # user-local extract
        str(Path.home() / 'AppData' / 'Local' / 'Microsoft' / 'WinGet' / 'Packages' /
            'Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe' / 'ffmpeg-7.1-full_build' / 'bin'),
    ]

    for candidate in common_paths:
        if Path(candidate).is_dir() and (Path(candidate) / 'ffmpeg.exe').exists():
            os.environ['PATH'] = candidate + os.pathsep + os.environ.get('PATH', '')
            print(f"[Pilot] ffmpeg found at {candidate} — added to PATH automatically")
            return

    # Not found in any common location — warn but don't fail (WAV uploads still work)
    print(
        "[Pilot] Note: ffmpeg not found. WAV uploads and live recording work fine.\n"
        "  For M4A/MP3 uploads, install ffmpeg:\n"
        "    winget install ffmpeg\n"
        "  or: choco install ffmpeg\n"
        "  Then restart Pilot."
    )


# Load user config on module import
_ensure_ffmpeg_on_path()
Config.load_user_config()


if __name__ == '__main__':
    # Test configuration
    print("Testing Pilot configuration...")
    print(f"Base directory: {Config.BASE_DIR}")
    print(f"User documents: {Config.USER_DOCS_DIR}")
    print(f"Meetings directory: {Config.MEETINGS_DIR}")
    print(f"Summaries directory: {Config.SUMMARIES_DIR}")
    print(f"Microphone device: {Config.MICROPHONE_DEVICE_INDEX or 'Auto-detect'}")
    print()

    errors = Config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  ✗ {error}")
    else:
        print("✓ Configuration is valid!")
        print(f"  Chunk duration: {Config.AUDIO_CHUNK_DURATION}s")
        print(f"  Sample rate: Auto-detected from device (typically 48000 Hz)")

    print()
    print("Creating directories...")
    Config.create_directories()
    print("✓ All directories created/verified")
