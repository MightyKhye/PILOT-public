"""Regenerate HTML for existing meeting."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.html_summary_generator import HTMLSummaryGenerator
from src.config import Config
import logging

logging.basicConfig(level=logging.INFO)

# Find the latest meeting
meetings_dir = Config.MEETINGS_DIR
md_files = list(meetings_dir.glob("meeting_*.md"))

if not md_files:
    print("No meeting files found")
    sys.exit(1)

# Sort by modification time, get most recent
latest_md = sorted(md_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]
print(f"Found meeting: {latest_md}")

# Read markdown content
with open(latest_md, 'r', encoding='utf-8') as f:
    markdown_content = f.read()

# Find corresponding snippets
meeting_id = latest_md.stem.replace('meeting_', '')
snippets_dir = Config.SNIPPETS_DIR

snippet_paths = {}
if snippets_dir.exists():
    for snippet_file in snippets_dir.glob(f"snippet_{meeting_id.replace('-', '')}*.wav"):
        # Extract action item ID from filename (would need actual mapping)
        # For now, just collect all snippets with proper IDs
        print(f"Found snippet: {snippet_file.name}")

        # Parse the snippet filename to get the chunk timestamp and text
        # Format: snippet_YYYYMMDD_HHMMSS_mmm_text.wav
        parts = snippet_file.stem.split('_')
        if len(parts) >= 4:
            # Create a hash from the text portion (simplified)
            import hashlib
            text_part = '_'.join(parts[4:])  # Everything after timestamp
            action_hash = hashlib.md5(text_part.encode()).hexdigest()[:8]
            snippet_paths[action_hash] = snippet_file

print(f"Found {len(snippet_paths)} snippets")

# Generate HTML
generator = HTMLSummaryGenerator()
html_path = generator.generate_html(
    markdown_summary=markdown_content,
    snippet_paths=snippet_paths,
    meeting_id=meeting_id,
    meeting_dir=meetings_dir
)

if html_path:
    print(f"\nHTML generated: {html_path}")

    # Copy to Downloads
    import shutil
    downloads_path = Path.home() / 'Downloads' / f"Meeting_Summary_{meeting_id}.html"
    shutil.copy(html_path, downloads_path)
    print(f"Copied to Downloads: {downloads_path}")

    # Open in browser
    import os
    if sys.platform == 'win32':
        os.startfile(downloads_path)
    print("\nOpened in your default browser!")
else:
    print("Failed to generate HTML")
