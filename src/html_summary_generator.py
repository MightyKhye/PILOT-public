"""Generate HTML meeting summaries with embedded audio snippets."""

import logging
from pathlib import Path
from typing import Dict, Optional, List
import re
import difflib

logger = logging.getLogger(__name__)


class HTMLSummaryGenerator:
    """Convert markdown summaries to HTML with embedded audio players."""

    def generate_html(self, markdown_summary: str, snippet_paths: Dict[str, Path],
                      meeting_id: str, meeting_dir: Path, complete_recording_path: Optional[Path] = None,
                      action_items_with_snippets: Optional[List[dict]] = None,
                      utterances: Optional[List[dict]] = None,
                      full_transcript: Optional[str] = None) -> Path:
        """
        Generate an HTML version of the meeting summary with embedded audio.

        Args:
            markdown_summary: The markdown summary text
            snippet_paths: Dict mapping action item IDs to snippet Path objects
            meeting_id: Meeting ID for filename
            meeting_dir: Directory where meeting files are stored
            complete_recording_path: Optional path to complete audio recording

        Returns:
            Path to generated HTML file
        """
        try:
            # Parse markdown into sections
            sections = self._parse_markdown(markdown_summary)

            # Debug: log which transcript source will be used
            sections_transcript_len = len(sections.get('transcript', ''))
            full_transcript_len = len(full_transcript) if full_transcript else 0
            logger.info(f"DEBUG: Received full_transcript param, length={len(full_transcript or '')} chars")
            logger.info(f"DEBUG: sections.get('transcript') length={len(sections.get('transcript', ''))} chars")
            logger.info(f"DEBUG: Using full_transcript={bool(full_transcript)}")
            logger.info(
                f"[transcript] generate_html: "
                f"full_transcript={'yes, ' + str(full_transcript_len) + ' chars' if full_transcript else 'None/empty'}, "
                f"sections[transcript]={sections_transcript_len} chars — "
                f"using {'full_transcript (injected)' if full_transcript else 'sections[transcript] (from Claude output)'}"
            )

            # Generate HTML
            html_content = self._generate_html_content(sections, snippet_paths, complete_recording_path, action_items_with_snippets, utterances, full_transcript)

            # Save HTML file
            html_filename = f"meeting_{meeting_id}.html"
            html_path = meeting_dir / html_filename

            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"HTML summary generated: {html_path}")
            return html_path

        except Exception as e:
            logger.error(f"Failed to generate HTML summary: {e}", exc_info=True)
            return None

    def _parse_markdown(self, markdown: str) -> dict:
        """Parse markdown into structured sections."""
        sections = {
            'title': '',
            'metadata': '',
            'action_items': [],
            'decisions': [],
            'clarifications': [],
            'synopsis': '',
            'participants': '',
            'transcript': ''
        }

        lines = markdown.split('\n')
        current_section = None
        buffer = []

        for line in lines:
            # Check for section headers (handle plain text, ## markdown, and **bold** markdown)
            line_stripped = line.strip().lstrip('#').strip('*').strip()

            if line_stripped == 'ACTION ITEMS':
                if buffer and current_section:
                    sections[current_section] = '\n'.join(buffer)
                current_section = 'action_items'
                buffer = []
            elif line_stripped == 'DECISIONS':
                if buffer and current_section:
                    if current_section == 'action_items':
                        sections['action_items'] = buffer.copy()
                    buffer = []
                current_section = 'decisions'
            elif line_stripped == 'ITEMS REQUIRING CLARIFICATION':
                if buffer and current_section:
                    if current_section == 'decisions':
                        sections['decisions'] = buffer.copy()
                    buffer = []
                current_section = 'clarifications'
            elif line_stripped == 'MEETING SYNOPSIS':
                if buffer and current_section:
                    if current_section == 'clarifications':
                        sections['clarifications'] = buffer.copy()
                    buffer = []
                current_section = 'synopsis'
            elif line_stripped == 'PARTICIPANTS':
                if buffer and current_section:
                    if current_section == 'synopsis':
                        sections['synopsis'] = '\n'.join(buffer)
                    buffer = []
                current_section = 'participants'
            elif line_stripped == 'COMPLETE TRANSCRIPT':
                if buffer and current_section:
                    if current_section == 'participants':
                        sections['participants'] = '\n'.join(buffer)
                    buffer = []
                current_section = 'transcript'
            elif line.startswith('━━━') or line.strip() == '---':
                continue  # Skip separator lines
            elif not current_section and line.strip():
                # Title/metadata area
                if 'REMS' in line or 'MEETING' in line:
                    sections['title'] = line.strip()
                elif 'Date:' in line or 'Transcription Quality:' in line:
                    # Skip quality line when confidence is 0.0% (model doesn't provide scores)
                    if 'Transcription Quality: 0.0%' not in line:
                        sections['metadata'] += line.strip() + '<br>'
            else:
                buffer.append(line)

        # Save remaining buffer
        if buffer and current_section:
            if current_section == 'transcript':
                sections['transcript'] = '\n'.join(buffer)
            elif current_section in ['action_items', 'decisions', 'clarifications']:
                sections[current_section] = buffer.copy()
            else:
                sections[current_section] = '\n'.join(buffer)

        return sections

    def _generate_html_content(self, sections: dict, snippet_paths: Dict[str, Path], complete_recording_path: Optional[Path] = None, action_items_with_snippets: Optional[List[dict]] = None, utterances: Optional[List[dict]] = None, full_transcript: Optional[str] = None) -> str:
        """Generate complete HTML document."""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{sections.get('title', 'Meeting Summary')}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}

        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            border-radius: 8px;
        }}

        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 15px;
            margin-bottom: 20px;
            font-size: 28px;
        }}

        h2 {{
            color: #2c3e50;
            margin-top: 35px;
            margin-bottom: 15px;
            font-size: 20px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }}

        .metadata {{
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 30px;
            padding: 15px;
            background: #ecf0f1;
            border-radius: 4px;
        }}

        .action-item {{
            margin: 15px 0;
            padding: 15px;
            border-left: 4px solid #f39c12;
            border-radius: 4px;
            background: #fff9e6;
            list-style: none;
        }}

        .action-content {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            font-size: 15px;
            color: #2c3e50;
        }}

        .action-text {{
            flex: 1;
            padding-right: 10px;
        }}

        .audio-player {{
            margin-top: 10px;
            padding: 10px;
            background: white;
            border-radius: 4px;
            border: 1px solid #ddd;
        }}

        .timestamp-info {{
            margin-top: 10px;
            padding: 8px 12px;
            background: #e3f2fd;
            border-radius: 4px;
            border-left: 3px solid #2196f3;
            font-family: monospace;
        }}

        .timestamp-label {{
            font-weight: bold;
            color: #1976d2;
            margin-right: 8px;
        }}

        .timestamp-value {{
            color: #0d47a1;
            font-size: 14px;
        }}

        .audio-label {{
            font-size: 13px;
            color: #7f8c8d;
            margin-bottom: 5px;
            display: block;
        }}

        audio {{
            width: 100%;
            height: 32px;
        }}

        .decision {{
            margin: 10px 0;
            padding: 12px;
            background: #e8f4f8;
            border-left: 4px solid #3498db;
            border-radius: 4px;
        }}

        .clarification {{
            margin: 10px 0;
            padding: 12px;
            background: #fef5e7;
            border-left: 4px solid #e67e22;
            border-radius: 4px;
        }}

        .synopsis {{
            margin: 20px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 4px;
            line-height: 1.8;
        }}

        .synopsis p {{
            margin-bottom: 15px;
        }}

        .transcript {{
            margin: 20px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            white-space: pre-wrap;
            max-height: 600px;
            overflow-y: auto;
        }}

        .utterance {{
            margin: 12px 0;
            padding: 10px;
            background: white;
            border-radius: 4px;
            border-left: 3px solid #4caf50;
        }}

        .speaker-label {{
            font-weight: bold;
            color: #2e7d32;
            margin-right: 8px;
        }}

        .timestamp-small {{
            color: #757575;
            font-size: 11px;
            margin-right: 10px;
        }}

        .utterance-text {{
            color: #333;
            line-height: 1.6;
            font-family: Arial, sans-serif;
            font-size: 14px;
        }}

        .confidence {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: bold;
            margin-left: 8px;
        }}

        .confidence-high {{
            background: #d4edda;
            color: #155724;
        }}

        .confidence-medium {{
            background: #fff3cd;
            color: #856404;
        }}

        .confidence-low {{
            background: #f8d7da;
            color: #721c24;
        }}

        ul {{
            list-style: none;
            padding: 0;
        }}

        .separator {{
            border-top: 2px solid #e0e0e0;
            margin: 30px 0;
        }}

        .audio-timestamp {{
            margin-top: 10px;
        }}

        .play-button {{
            background: #4caf50;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-size: 14px;
            cursor: pointer;
            transition: background 0.3s;
            font-weight: 500;
        }}

        .play-button:hover {{
            background: #45a049;
        }}

        .play-button:active {{
            background: #3d8b40;
        }}

        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            .container {{
                box-shadow: none;
            }}
            .play-button {{
                display: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{sections.get('title', 'Meeting Summary')}</h1>
        <div class="metadata">{sections.get('metadata', '')}</div>

        {self._generate_action_items_html(sections.get('action_items', []), snippet_paths, action_items_with_snippets)}

        {self._generate_decisions_html(sections.get('decisions', []))}

        {self._generate_clarifications_html(sections.get('clarifications', []))}

        <div class="separator"></div>

        <h2>Meeting Synopsis</h2>
        <div class="synopsis">
            {self._format_paragraphs(sections.get('synopsis', ''))}
        </div>

        <div class="separator"></div>

        <h2>Participants</h2>
        <div>
            {self._format_list(sections.get('participants', ''))}
        </div>

        <div class="separator"></div>

        <h2>Complete Transcript</h2>
        {self._generate_complete_recording_player(complete_recording_path)}
        {self._generate_transcript_html(full_transcript or sections.get('transcript', ''), utterances)}
    </div>

    <script>
        // Function to play audio at specific timestamp
        function playAtTimestamp(seconds) {{
            const audio = document.getElementById('mainAudioPlayer');
            if (audio) {{
                // Scroll to audio player
                audio.scrollIntoView({{ behavior: 'smooth', block: 'center' }});

                // Seek to timestamp and play
                audio.currentTime = Math.max(0, seconds - 2); // Start 2 seconds before for context
                audio.play();

                // Highlight the audio player briefly
                const container = audio.parentElement;
                container.style.background = '#fff9c4';
                setTimeout(() => {{
                    container.style.background = '#e8f5e9';
                }}, 2000);
            }}
        }}
    </script>
</body>
</html>"""

        return html

    def _generate_transcript_html(self, transcript_text: str, utterances: Optional[List[dict]] = None) -> str:
        """Generate HTML for transcript."""
        logger.info(f"[transcript] rendering {len(transcript_text)} chars into HTML")
        return f'<div class="transcript">{transcript_text}</div>'

    def _generate_complete_recording_player(self, complete_recording_path: Optional[Path]) -> str:
        """Generate HTML for complete recording audio player."""
        if not complete_recording_path or not complete_recording_path.exists():
            return ""

        # Use relative path from HTML file
        relative_path = complete_recording_path.name

        return f'''
        <div style="margin: 20px 0; padding: 15px; background: #e8f5e9; border-left: 4px solid #4caf50; border-radius: 4px;">
            <div style="font-weight: bold; margin-bottom: 10px; color: #2e7d32;">
                🎧 Complete Audio Recording
            </div>
            <audio id="mainAudioPlayer" controls style="width: 100%;">
                <source src="{relative_path}" type="audio/wav">
                Your browser does not support the audio element.
            </audio>
        </div>'''

    def _generate_action_items_html(self, action_items: list, snippet_paths: Dict[str, Path], action_items_with_snippets: Optional[List[dict]] = None) -> str:
        """Generate HTML for action items with audio players."""
        if not action_items and not action_items_with_snippets:
            return ""

        import hashlib

        html = '<h2>Action Items</h2><ul>'

        # Fallback: if markdown parsing yielded no action item lines, render from snippets data directly
        if not action_items and action_items_with_snippets:
            for item in action_items_with_snippets:
                text = item.get('text', '')
                assignee = item.get('assignee', '')
                start_time = item.get('start_time')
                display_text = f"{assignee}: {text}" if assignee else text
                play_html = ''
                if start_time is not None:
                    start_mins = int(start_time // 60)
                    start_secs = int(start_time % 60)
                    play_html = f'''
                    <div class="audio-timestamp">
                        <button class="play-button" onclick="playAtTimestamp({start_time})">
                            ▶ Play from {start_mins:02d}:{start_secs:02d}
                        </button>
                    </div>'''
                html += f'''
            <li class="action-item">
                <div class="action-content">
                    <span class="action-text">{display_text}</span>
                </div>
                {play_html}
            </li>'''
            html += '</ul>'
            return html

        for item_line in action_items:
            if not item_line.strip() or not item_line.strip().startswith('-'):
                continue

            # Parse action item
            # Format: "- **Assignee**: Action text | Confidence: level"
            # Or old format: "- [ ] [Assignee]: Action text - Confidence: level"
            item_text = item_line.strip()
            if item_text.startswith('- [ ]'):
                item_text = item_text[6:]  # Remove "- [ ] "
            else:
                item_text = item_text[2:]  # Remove "- "

            # Replace markdown bold with brackets for consistency
            item_text = re.sub(r'\*\*([^*]+)\*\*:', r'[\1]:', item_text)

            # Extract confidence level
            confidence = ''
            confidence_class = ''
            if 'Confidence:' in item_text:
                conf_match = re.search(r'Confidence:\s*(high|medium|low)', item_text, re.IGNORECASE)
                if conf_match:
                    confidence = conf_match.group(1).lower()
                    confidence_class = f'confidence-{confidence}'
                    confidence = f'<span class="confidence {confidence_class}">{confidence.upper()}</span>'

            # Try to find matching snippet
            snippet_html = ''

            # Extract assignee and action for hash matching
            match = re.search(r'^(?:([^:]+):\s*)?(.+?)(?:\s*\(Due:|\s*-\s*Confidence:|$)', item_text)
            if match:
                assignee = match.group(1).strip() if match.group(1) else ""
                action_text = match.group(2).strip()

                # Generate action item ID
                action_item_id = hashlib.md5(f"{action_text}_{assignee}".encode()).hexdigest()[:8]

                # Check if snippet exists by hash
                snippet_path = None
                if action_item_id in snippet_paths:
                    snippet_path = snippet_paths[action_item_id]
                elif action_items_with_snippets:
                    # Try fuzzy matching against the stored action items
                    snippet_path = self._find_snippet_by_fuzzy_match(action_text, assignee, action_items_with_snippets)
                else:
                    # Only use directory fallback if no action_items_with_snippets provided
                    snippet_path = self._find_snippet_by_text(action_text, snippet_paths)

                # Check for timestamp info from action_items_with_snippets
                timestamp_html = ''
                start_time = None
                end_time = None
                if action_items_with_snippets:
                    # Try exact match first
                    for item in action_items_with_snippets:
                        if action_text.lower().strip() == item.get('text', '').lower().strip():
                            start_time = item.get('start_time')
                            end_time = item.get('end_time')
                            break

                    # If no exact match, try fuzzy matching
                    if start_time is None:
                        from difflib import SequenceMatcher
                        best_ratio = 0
                        best_item = None
                        for item in action_items_with_snippets:
                            ratio = SequenceMatcher(None, action_text.lower().strip(), item.get('text', '').lower().strip()).ratio()
                            if ratio > best_ratio:
                                best_ratio = ratio
                                best_item = item

                        if best_ratio > 0.45 and best_item:
                            start_time = best_item.get('start_time')
                            end_time = best_item.get('end_time')

                # Format timestamp with Play button
                if start_time is not None:
                    start_mins = int(start_time // 60)
                    start_secs = int(start_time % 60)
                    snippet_html = f'''
                    <div class="audio-timestamp">
                        <button class="play-button" onclick="playAtTimestamp({start_time})">
                            ▶ Play from {start_mins:02d}:{start_secs:02d}
                        </button>
                    </div>'''
                else:
                    snippet_html = ''

            # Clean action item text (remove confidence from display)
            clean_text = item_text.replace(f'- Confidence: {confidence}', '').replace(f'| Confidence: {confidence}', '')

            html += f'''
            <li class="action-item">
                <div class="action-content">
                    <span class="action-text">{clean_text}</span>
                    {confidence}
                </div>
                {snippet_html}
            </li>'''

        html += '</ul>'
        return html

    def _generate_decisions_html(self, decisions: list) -> str:
        """Generate HTML for decisions."""
        if not decisions:
            return ""

        html = '<h2>Decisions</h2><ul>'

        for decision_line in decisions:
            if not decision_line.strip() or not decision_line.strip().startswith('- '):
                continue

            decision_text = decision_line.strip()[2:]  # Remove "- "

            # Extract confidence
            confidence = ''
            if 'Confidence:' in decision_text:
                conf_match = re.search(r'Confidence:\s*(high|medium|low)', decision_text, re.IGNORECASE)
                if conf_match:
                    conf_level = conf_match.group(1).lower()
                    confidence_class = f'confidence-{conf_level}'
                    confidence = f' <span class="confidence {confidence_class}">{conf_level.upper()}</span>'
                    decision_text = decision_text.replace(f'(Confidence: {conf_match.group(1)})', '')

            html += f'<li><div class="decision">{decision_text}{confidence}</div></li>'

        html += '</ul>'
        return html

    def _generate_clarifications_html(self, clarifications: list) -> str:
        """Generate HTML for items requiring clarification."""
        if not clarifications:
            return ""

        html = '<h2>Items Requiring Clarification</h2><ul>'

        for item_line in clarifications:
            if not item_line.strip() or not item_line.strip().startswith('- '):
                continue

            item_text = item_line.strip()[2:]  # Remove "- "
            html += f'<li><div class="clarification">{item_text}</div></li>'

        html += '</ul>'
        return html

    def _format_paragraphs(self, text: str) -> str:
        """Format text into HTML paragraphs."""
        paragraphs = text.strip().split('\n\n')
        return ''.join(f'<p>{p.strip()}</p>' for p in paragraphs if p.strip())

    def _format_list(self, text: str) -> str:
        """Format list items."""
        lines = text.strip().split('\n')
        html = '<ul>'
        for line in lines:
            if line.strip().startswith('- '):
                html += f'<li>{line.strip()[2:]}</li>'
        html += '</ul>'
        return html

    def _find_snippet_by_text(self, action_text: str, snippet_paths: Dict[str, Path]) -> Optional[Path]:
        """
        Find snippet by fuzzy matching action text with snippet filenames.

        Args:
            action_text: The action item text to match
            snippet_paths: Dict of snippet paths (values are what we search)

        Returns:
            Path to matching snippet, or None
        """
        from difflib import SequenceMatcher

        # Normalize action text for comparison
        action_normalized = re.sub(r'[^a-zA-Z0-9\s]', '', action_text.lower())

        best_match = None
        best_ratio = 0.0

        # Check all snippet paths (both dict values and discover from directory)
        all_snippets = set(snippet_paths.values())

        # Also check snippets directory if we can find it
        try:
            from .config import Config
            if Config.SNIPPETS_DIR.exists():
                all_snippets.update(Config.SNIPPETS_DIR.glob("snippet_*.wav"))
        except:
            pass

        for snippet_path in all_snippets:
            # Extract text portion from filename
            # Format: snippet_YYYYMMDD_HHMMSS_mmm_Action_text_here.wav
            filename = snippet_path.stem
            parts = filename.split('_')

            if len(parts) > 4:
                # Text is everything after the timestamp parts
                text_part = '_'.join(parts[4:])
                # Normalize for comparison
                snippet_normalized = re.sub(r'[^a-zA-Z0-9\s]', '', text_part.lower())

                # Calculate similarity
                ratio = SequenceMatcher(None, action_normalized, snippet_normalized).ratio()

                if ratio > best_ratio and ratio > 0.5:  # Threshold of 50% match
                    best_ratio = ratio
                    best_match = snippet_path

        if best_match:
            logger.info(f"Fuzzy matched action '{action_text[:50]}...' to snippet '{best_match.name}' (ratio: {best_ratio:.2f})")

        return best_match

    def _find_snippet_by_fuzzy_match(self, action_text: str, assignee: str, action_items_with_snippets: List[dict]) -> Optional[Path]:
        """
        Find snippet by fuzzy matching against stored action items.

        Args:
            action_text: The action item text to match
            assignee: The assignee name
            action_items_with_snippets: List of dicts with 'text', 'assignee', 'snippet_path'

        Returns:
            Path to matching snippet, or None
        """
        from difflib import SequenceMatcher

        best_match = None
        best_ratio = 0.0

        # Normalize for comparison
        action_normalized = action_text.lower().strip()

        for item in action_items_with_snippets:
            stored_text = item['text'].lower().strip()
            stored_assignee = (item.get('assignee') or '').lower().strip()
            assignee_normalized = (assignee or '').lower().strip()

            # Calculate similarity for action text
            text_ratio = SequenceMatcher(None, action_normalized, stored_text).ratio()

            # Boost score if assignee matches
            if assignee_normalized and stored_assignee and assignee_normalized == stored_assignee:
                text_ratio += 0.2  # Boost for matching assignee

            if text_ratio > best_ratio and text_ratio > 0.45:  # 45% threshold
                best_ratio = text_ratio
                best_match = item['snippet_path']

        if best_match:
            logger.info(f"Fuzzy matched action '{action_text[:50]}...' to stored item (ratio: {best_ratio:.2f})")

        return best_match
