"""AI analysis module using Claude API for meeting insights."""

import json
import logging
import time
from typing import Optional, Dict, List
from datetime import datetime
from anthropic import Anthropic, APIError

from .config import Config
from .rate_limiter import APIRateLimiter

logger = logging.getLogger(__name__)


class MeetingAnalyzer:
    """Analyzes meeting transcriptions using Claude AI."""

    def __init__(self, api_key: Optional[str] = None, max_calls_per_minute: int = 10):
        """
        Initialize analyzer.

        Args:
            api_key: Anthropic API key (default from config)
            max_calls_per_minute: Maximum API calls per minute (default: 10)
        """
        self.api_key = api_key or Config.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key is required")

        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-sonnet-4-6"

        # Context management
        self.conversation_history: List[str] = []
        self.meeting_context = {
            'action_items': [],
            'decisions': [],
            'key_points': [],
            'participants': set()
        }
        # Set by generate_summary() — the annotated+Haiku-cleaned full transcript.
        # The HTML generator reads this directly so the transcript is never truncated
        # by Claude's max_tokens output limit.
        self.last_full_transcript: str = ""

        # API RATE LIMITING - Prevent IP bans and runaway costs
        self.rate_limiter = APIRateLimiter(
            max_calls_per_minute=max_calls_per_minute,
            circuit_breaker_threshold=5
        )
        logger.info(f"Rate limiter initialized: max {max_calls_per_minute} calls/minute")

    def analyze_chunk(
        self,
        transcription: str,
        max_retries: int = 3
    ) -> Optional[Dict]:
        """
        Analyze a transcription chunk for action items and decisions.

        Args:
            transcription: Transcribed text to analyze
            max_retries: Maximum retry attempts

        Returns:
            Dict with extracted insights or None if failed
            {
                'action_items': [{'item': str, 'assignee': str or None}],
                'decisions': [str],
                'key_points': [str],
                'participants': [str]
            }
        """
        if not transcription or not transcription.strip():
            logger.warning("Empty transcription provided")
            return None

        # Build context from previous chunks
        context_str = self._build_context()

        # Create analysis prompt
        prompt = self._create_analysis_prompt(transcription, context_str)

        for attempt in range(max_retries):
            try:
                # API RATE LIMITING - Check if we can make a call
                can_call, wait_seconds = self.rate_limiter.can_make_call()

                if not can_call:
                    if self.rate_limiter.circuit_open:
                        logger.error(f"Circuit breaker open - cannot make API call. Wait {wait_seconds:.1f}s")
                        if attempt < max_retries - 1:
                            time.sleep(wait_seconds)
                            continue
                        else:
                            logger.error("Circuit breaker prevented all retry attempts")
                            return None
                    else:
                        # Rate limited - wait and retry
                        logger.warning(f"Rate limited - waiting {wait_seconds:.1f}s before retry")
                        time.sleep(wait_seconds)
                        continue

                logger.info(f"Analyzing transcription (attempt {attempt + 1}/{max_retries})")

                start_time = time.time()

                # Call Claude API
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2000,
                    temperature=0.3,  # Lower temperature for more focused extraction
                    system=Config.PILOT_SYSTEM_CONTEXT,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )

                duration = time.time() - start_time

                # Extract text from response
                result_text = response.content[0].text

                # Parse JSON response
                result = self._parse_analysis_result(result_text)

                if result:
                    # Record successful API call
                    self.rate_limiter.record_call(success=True)

                    # Update context
                    self._update_context(transcription, result)

                    logger.info(f"Analysis completed in {duration:.1f}s: "
                               f"{len(result.get('action_items', []))} action items, "
                               f"{len(result.get('decisions', []))} decisions")

                    return result
                else:
                    logger.error("Failed to parse analysis result")
                    # Record failed API call
                    self.rate_limiter.record_call(success=False)

                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None

            except APIError as e:
                logger.error(f"Claude API error (attempt {attempt + 1}): {e}")
                # Record failed API call
                self.rate_limiter.record_call(success=False)

                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries reached, analysis failed")
                    # Log rate limiter stats
                    stats = self.rate_limiter.get_stats()
                    logger.info(f"Rate limiter stats: {stats}")
                    return None

            except Exception as e:
                logger.error(f"Unexpected error during analysis: {e}")
                # Record failed API call
                self.rate_limiter.record_call(success=False)
                return None

        return None

    def _create_analysis_prompt(self, transcription: str, context: str) -> str:
        """Create the analysis prompt for Claude."""
        return f"""You are analyzing a meeting transcription in real-time.

{'Previous meeting context:\n' + context if context else 'This is the start of the meeting.'}

New transcription segment:
\"\"\"
{transcription}
\"\"\"

Extract the following with HIGH PRIORITY on action items and decisions:

1. **Action Items**: Tasks, follow-ups, or deliverables. Include:
   - What needs to be done
   - Who is responsible (if mentioned)
   - Deadline/timeframe (if mentioned)
   - Confidence: "high" if clearly stated, "medium" if implied, "low" if uncertain

2. **Decisions**: Any decisions made or agreed upon. Include:
   - The decision
   - Confidence: "high" if clearly stated, "medium" if implied

3. **Key Points**: Important discussion topics (REMS requirements, training, FDA compliance, safety, logistics)

4. **Participants**: Names and roles if identifiable

5. **Unclear Items**: Flag anything ambiguous, missing context, or requiring clarification

Return as JSON:
{{
  "action_items": [
    {{
      "item": "description",
      "assignee": "name or null",
      "deadline": "timeframe or null",
      "confidence": "high/medium/low"
    }}
  ],
  "decisions": [
    {{
      "decision": "what was decided",
      "confidence": "high/medium"
    }}
  ],
  "key_points": ["point 1", "point 2"],
  "participants": ["name (role if known)"],
  "unclear_items": ["what's unclear or needs clarification"]
}}

Focus on:
- Compliance and regulatory requirements
- Training and certification
- Approval and authorization items
- Documentation and reporting needs
- Safety and risk-related items
- Timelines and deadlines"""

    def _build_context(self) -> str:
        """Build context string from conversation history."""
        if not self.conversation_history:
            return ""

        # Use last 3 chunks for context (to avoid token limits)
        recent_chunks = self.conversation_history[-3:]

        context_parts = []

        if self.meeting_context['action_items']:
            items = self.meeting_context['action_items'][-5:]  # Last 5 items
            context_parts.append("Recent action items: " +
                               ", ".join(f"{item['item']}" for item in items))

        if self.meeting_context['decisions']:
            decisions = self.meeting_context['decisions'][-3:]
            # Handle both dict format (new) and string format (old)
            decision_texts = []
            for d in decisions:
                if isinstance(d, dict):
                    decision_texts.append(d.get('decision', str(d)))
                else:
                    decision_texts.append(str(d))
            context_parts.append("Recent decisions: " + ", ".join(decision_texts))

        if self.meeting_context['participants']:
            context_parts.append("Participants: " +
                               ", ".join(self.meeting_context['participants']))

        if recent_chunks:
            context_parts.append("\nRecent discussion:\n" +
                               "\n".join(f"- {chunk[:200]}..." for chunk in recent_chunks))

        return "\n".join(context_parts)

    def _parse_analysis_result(self, result_text: str) -> Optional[Dict]:
        """Parse Claude's JSON response."""
        try:
            # Try to find JSON in the response
            # Claude might include text before/after JSON
            start_idx = result_text.find('{')
            end_idx = result_text.rfind('}') + 1

            if start_idx == -1 or end_idx == 0:
                logger.error("No JSON found in response")
                return None

            json_str = result_text[start_idx:end_idx]
            result = json.loads(json_str)

            # Validate structure
            if not isinstance(result, dict):
                logger.error("Result is not a dictionary")
                return None

            # Ensure all required fields exist
            result.setdefault('action_items', [])
            result.setdefault('decisions', [])
            result.setdefault('key_points', [])
            result.setdefault('participants', [])
            result.setdefault('unclear_items', [])

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Response text: {result_text}")
            return None

    def _update_context(self, transcription: str, analysis: Dict):
        """Update conversation context with new analysis."""
        # Add transcription to history
        self.conversation_history.append(transcription)

        # Keep only recent history (last 10 chunks)
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]

        # Update meeting context
        self.meeting_context['action_items'].extend(analysis.get('action_items', []))
        self.meeting_context['decisions'].extend(analysis.get('decisions', []))
        self.meeting_context['key_points'].extend(analysis.get('key_points', []))

        # Update participants
        for participant in analysis.get('participants', []):
            self.meeting_context['participants'].add(participant)

    def clean_transcription(self, raw_text: str) -> str:
        """
        Fix domain-specific transcription errors using Claude Haiku.

        Runs a fast, cheap cleanup pass on the raw ASR output before summary
        generation. Preserves meaning and inline confidence markers exactly.

        Args:
            raw_text: Raw transcript text (may contain ASR errors and
                      inline confidence markers like "(confidence: 45% - unclear)")

        Returns:
            Corrected transcript text, or original if cleanup fails.
        """
        if not raw_text or not raw_text.strip():
            return raw_text

        try:
            # Estimate a generous output token budget (words × 1.5 + buffer)
            word_count = len(raw_text.split())
            max_tokens = min(8192, max(512, int(word_count * 1.5) + 300))

            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                temperature=0,
                system=Config.PILOT_SYSTEM_CONTEXT,
                messages=[{
                    "role": "user",
                    "content": f"""Fix obvious ASR (automatic speech recognition) errors in this meeting transcript. Rules:
- Preserve the exact meaning, sequence, and all spoken content
- Do NOT paraphrase, summarize, or reorder anything
- Preserve all footnote markers exactly as-is, e.g. [1], [2], [3] — do not move, remove, or reformat them
- Preserve the "---\nTranscript Notes:" section at the end verbatim (do not alter footnote text)
- Preserve speaker labels and timestamps if present

Common ASR corrections:
- Fix product names or acronyms that are phonetically misspelled
- Fix articles before acronyms: "a HCP" → "an HCP", "a FDA" → "an FDA"
- Fix run-together or dropped words where clearly a transcription artifact
- Fix homophone errors for proper nouns specific to this meeting's domain

Return the corrected transcript only. No commentary, no preamble.

Transcript:
{raw_text}"""
                }]
            )

            corrected = response.content[0].text.strip()
            logger.info(f"Transcription cleanup: {word_count} words cleaned via Haiku")
            return corrected

        except Exception as e:
            logger.warning(f"Transcription cleanup failed, using raw text: {e}")
            return raw_text

    def generate_summary(self, transcription_confidence: float = 0.0, transcription_words: list = None, action_item_snippets: dict = None) -> str:
        """
        Generate a comprehensive meeting summary with prioritized structure.

        Args:
            transcription_confidence: Average transcription confidence score
            transcription_words: List of word-level confidence data from transcriptions
            action_item_snippets: Dict mapping action item IDs to snippet file paths

        Returns:
            Formatted summary string
        """
        if not self.conversation_history:
            return "No meeting data to summarize."

        try:
            # STEP 1: Build the base transcript from all chunks in conversation_history.
            # Set last_full_transcript immediately — this is the guaranteed-complete fallback.
            # Both annotation and Haiku cleanup can produce shorter output; we only upgrade
            # last_full_transcript if those steps don't shorten it significantly.
            base_transcript = "\n\n".join(self.conversation_history)
            self.last_full_transcript = base_transcript
            logger.info(f"DEBUG: Set last_full_transcript, length={len(self.last_full_transcript)} chars")
            logger.info(
                f"[transcript] base: {len(base_transcript)} chars / "
                f"{len(base_transcript.split())} words / "
                f"{len(self.conversation_history)} segments"
            )

            # STEP 2: Annotate with confidence markers.
            # WARNING: _annotate_transcript_confidence() RECONSTRUCTS the transcript from
            # word objects when transcription_words is provided — it does NOT annotate the
            # base_transcript in-place. If word data only covers a portion of the meeting
            # (e.g., only last 10 in-memory chunks out of 113), the result will be shorter.
            annotated = self._annotate_transcript_confidence(base_transcript, transcription_words)
            if transcription_words and len(annotated) < len(base_transcript) * 0.8:
                logger.warning(
                    f"[transcript] Annotation produced {len(annotated)} chars "
                    f"({len(annotated) / max(len(base_transcript), 1):.0%} of "
                    f"{len(base_transcript)} base chars) — "
                    f"word data likely covers only a portion of the meeting. "
                    f"Using full base transcript to preserve all content."
                )
                full_transcript = base_transcript
            else:
                full_transcript = annotated
                logger.info(f"[transcript] after annotation: {len(full_transcript)} chars")

            # STEP 3: Haiku ASR cleanup.
            # For long meetings (56 min ≈ 7,300 words ≈ 11,000 tokens), Haiku's
            # max_tokens cap (8,192) can truncate the output. Only use the cleaned
            # version if it is at least 90% of the input length.
            cleaned = self.clean_transcription(full_transcript)
            if len(cleaned) >= len(full_transcript) * 0.9:
                full_transcript = cleaned
                self.last_full_transcript = cleaned
                logger.info(f"[transcript] after Haiku cleanup: {len(cleaned)} chars — stored in last_full_transcript")
            else:
                logger.warning(
                    f"[transcript] Haiku cleanup produced {len(cleaned)} chars "
                    f"({len(cleaned) / max(len(full_transcript), 1):.0%} of "
                    f"{len(full_transcript)}) — output likely hit max_tokens. "
                    f"Using pre-cleanup transcript; last_full_transcript = "
                    f"{len(self.last_full_transcript)} chars (base)."
                )
                # full_transcript stays as annotated/base; last_full_transcript stays as base

            # Create summary prompt with new structure
            # NOTE: We intentionally do NOT ask Claude to output the transcript.
            # Claude still receives the full transcript as input for accurate extraction,
            # but the HTML generator injects it directly from last_full_transcript.
            # This frees all 4000 output tokens for the structured sections.
            prompt = f"""You are creating a comprehensive summary of a meeting.

Complete transcript:
\"\"\"
{full_transcript}
\"\"\"

CRITICAL INSTRUCTION: ONLY use names that are EXPLICITLY STATED in the transcript. NEVER invent, guess, or hallucinate names. If a name is not clearly mentioned, use descriptive placeholders like [Team member], [IT lead], [Speaker], or [Unidentified]. Accuracy is more important than specificity.

Create a clean, clinical summary with this EXACT format (NO emojis, minimal formatting):

KEY MILESTONES & DATES

[Brief 1-2 sentence context of the meeting in an encouraging, action-oriented tone]
[Simple bullet list of key dates, milestones, and deadlines mentioned - keep it scannable]
- [Milestone/deliverable] - [Date]
- [Next meeting/demo] - [Date]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ACTION ITEMS

[List each with assignee, deadline, confidence. Use ONLY names explicitly mentioned in transcript. If unclear, use [Team member], [IT team], [Speaker], etc.]
- [Assignee - only if explicitly named]: [Action item] (Due: [deadline]) | Confidence: [high/medium/low]

DECISIONS

[List each decision with confidence]
- [Decision] (Confidence: [high/medium])

ITEMS REQUIRING CLARIFICATION

[List anything unclear]
- [Item]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MEETING SYNOPSIS

[2-3 paragraph professional overview covering main topics, key themes and outcomes]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PARTICIPANTS

[List with roles if identifiable]

Format professionally and clinically. Be specific. Use simple formatting."""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.3,  # Lower temperature for more factual output
                system=Config.PILOT_SYSTEM_CONTEXT,
                messages=[{"role": "user", "content": prompt}]
            )

            summary = response.content[0].text
            logger.info("Meeting summary generated successfully")

            # Add snippet links to action items if available
            if action_item_snippets:
                summary = self._add_snippet_links(summary, action_item_snippets)

            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return self._generate_fallback_summary()

    def _annotate_transcript_confidence(self, transcript: str, transcription_words: list = None) -> str:
        """
        Annotate transcript with footnote-style markers for low-confidence sections.

        Instead of noisy inline annotations like "[protected annually] (confidence: 33% - unclear)",
        appends a compact superscript-style marker [N] at the end of each flagged section and
        collects all notes into a "Transcript Notes:" footer. This keeps the reading flow clean
        while preserving all uncertainty information for Claude's summary.

        Args:
            transcript: Full transcript text
            transcription_words: List of word lists from each transcription chunk

        Returns:
            Annotated transcript with [N] footnote markers, followed by a
            "Transcript Notes:" section listing each flagged passage.
        """
        if not transcription_words:
            return transcript

        # Flatten all word data from multiple chunks
        all_words = []
        for chunk_words in transcription_words:
            if chunk_words and isinstance(chunk_words, list):
                all_words.extend(chunk_words)

        if not all_words:
            return transcript

        result_parts = []
        footnotes = []   # List of (marker_num, avg_conf, section_text)
        low_conf_buffer = []

        LOW_CONF_THRESHOLD = 0.70  # Flag sections below 70% confidence
        VERY_LOW_THRESHOLD = 0.50  # "may be inaccurate" vs "lower confidence"
        MIN_SECTION_WORDS = 3      # Ignore very short dips (single/double words)

        def flush_low_conf():
            nonlocal low_conf_buffer
            if not low_conf_buffer:
                return
            if len(low_conf_buffer) >= MIN_SECTION_WORDS:
                avg_conf = sum(c for _, c in low_conf_buffer) / len(low_conf_buffer)
                section_text = " ".join(w for w, _ in low_conf_buffer)
                marker_num = len(footnotes) + 1
                footnotes.append((marker_num, avg_conf, section_text))
                # Append marker directly after section text (no extra period)
                result_parts.append(f"{section_text}[{marker_num}]")
            else:
                # Too short to flag — include as plain text
                result_parts.extend(w for w, _ in low_conf_buffer)
            low_conf_buffer = []

        for word_data in all_words:
            word_text = word_data.get('text', '')
            confidence = word_data.get('confidence', 1.0)

            if confidence < LOW_CONF_THRESHOLD:
                low_conf_buffer.append((word_text, confidence))
            else:
                flush_low_conf()
                result_parts.append(word_text)

        flush_low_conf()

        annotated = " ".join(result_parts)

        if not footnotes:
            return annotated

        # Build footnote section
        notes_lines = ["\n\n---\nTranscript Notes:"]
        for num, avg_conf, text in footnotes:
            qualifier = "may be inaccurate" if avg_conf < VERY_LOW_THRESHOLD else "lower confidence"
            notes_lines.append(f'[{num}] Low confidence ({avg_conf:.0%}) — "{text}" {qualifier}')

        return annotated + "\n".join(notes_lines)

    def _generate_fallback_summary(self) -> str:
        """Generate a basic summary from collected context."""
        lines = ["ACTION ITEMS\n"]

        # Action Items first (priority)
        if self.meeting_context['action_items']:
            for item in self.meeting_context['action_items']:
                assignee = item.get('assignee') or "Unassigned"
                lines.append(f"- [ ] {assignee}: {item['item']}")
            lines.append("")
        else:
            lines.append("- No action items identified")
            lines.append("")

        # Decisions
        lines.append("DECISIONS\n")
        if self.meeting_context['decisions']:
            for decision in self.meeting_context['decisions']:
                # Handle both old format (string) and new format (dict)
                if isinstance(decision, dict):
                    conf = decision.get('confidence', 'unknown')
                    lines.append(f"- {decision.get('decision', decision)} (Confidence: {conf})")
                else:
                    lines.append(f"- {decision}")
            lines.append("")
        else:
            lines.append("- No decisions documented")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        lines.append("MEETING SYNOPSIS\n")
        lines.append("Meeting summary could not be generated. See key points below.")
        lines.append("")

        if self.meeting_context['key_points']:
            for point in self.meeting_context['key_points']:
                lines.append(f"- {point}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        lines.append("PARTICIPANTS\n")
        if self.meeting_context['participants']:
            lines.append(", ".join(sorted(self.meeting_context['participants'])))
        else:
            lines.append("No participants identified")

        return "\n".join(lines)

    def _add_snippet_links(self, summary: str, snippet_paths: dict) -> str:
        """
        Add clickable audio snippet links to action items in the summary.

        Args:
            summary: Generated summary markdown
            snippet_paths: Dict mapping action item IDs to snippet Path objects

        Returns:
            Summary with snippet links added
        """
        if not snippet_paths:
            return summary

        import hashlib
        import re
        from pathlib import Path

        # Find the ACTION ITEMS section
        lines = summary.split('\n')
        result_lines = []
        in_action_items = False

        for line in lines:
            # Check if we're in the ACTION ITEMS section
            if line.strip() == 'ACTION ITEMS':
                in_action_items = True
                result_lines.append(line)
                continue

            # Check if we've left the ACTION ITEMS section
            if in_action_items and (line.strip() == 'DECISIONS' or
                                   line.strip() == 'ITEMS REQUIRING CLARIFICATION' or
                                   line.startswith('━━━')):
                in_action_items = False
                result_lines.append(line)
                continue

            # If we're in ACTION ITEMS and it's an action item line
            if in_action_items and line.strip().startswith('- [ ]'):
                # Try to match the action item with a snippet
                snippet_link = self._find_snippet_for_action_line(line, snippet_paths)
                if snippet_link:
                    # Add snippet link at the end of the line
                    line = line.rstrip() + f"  \n  [🔊 Listen to context]({snippet_link})"

                result_lines.append(line)
            else:
                result_lines.append(line)

        return '\n'.join(result_lines)

    def _find_snippet_for_action_line(self, action_line: str, snippet_paths: dict) -> str:
        """
        Find matching snippet for an action item line.

        Args:
            action_line: Line from summary like "- [ ] John: Update spec..."
            snippet_paths: Dict mapping action IDs to Path objects

        Returns:
            Relative path to snippet file, or empty string if not found
        """
        import hashlib
        import re
        from pathlib import Path

        # Extract action text and assignee from line
        # Format: "- [ ] [Assignee]: [Action] (Due: ...) - Confidence: ..."
        match = re.search(r'- \[ \] (?:([^:]+): )?(.+?)(?:\s*\(Due:|$)', action_line)
        if not match:
            return ""

        assignee = match.group(1) if match.group(1) else ""
        action_text = match.group(2).strip()

        # Generate action item ID the same way as in meeting_manager
        action_item_id = hashlib.md5(f"{action_text}_{assignee}".encode()).hexdigest()[:8]

        # Look up snippet path
        if action_item_id in snippet_paths:
            snippet_path = snippet_paths[action_item_id]
            # Convert to relative path from meetings directory
            # Snippet is in meetings/snippets/, summary is in meetings/
            return f"snippets/{snippet_path.name}"

        return ""

    def reset(self):
        """Reset analyzer state for a new meeting."""
        self.conversation_history.clear()
        self.meeting_context = {
            'action_items': [],
            'decisions': [],
            'key_points': [],
            'participants': set()
        }
        self.last_full_transcript = ""
        logger.info("Analyzer state reset")

    def generate_status_check(self, meeting_history: List[Dict]) -> Dict:
        """
        Generate a comprehensive project management status report.

        Args:
            meeting_history: List of meeting data dicts from persistent memory

        Returns:
            Dict with:
                'status_report': str (formatted report)
                'confidence': str ('HIGH', 'MEDIUM', 'LOW')
                'confidence_explanation': str
                'data_quality': Dict (metrics about available data)
                'generated_at': str (timestamp with timezone)
        """
        try:
            logger.info("Generating comprehensive status check from meeting history...")

            # Get CURRENT date/time for accurate relative time calculations
            from datetime import datetime, timedelta
            current_datetime = datetime.now()
            # Format for display: "February 16, 2026 at 2:45 PM CT"
            current_date_formatted = current_datetime.strftime("%B %d, %Y at %I:%M %p CT")
            # Date only for calculations
            current_date_simple = current_datetime.strftime("%Y-%m-%d")
            yesterday_date = (current_datetime - timedelta(days=1)).strftime("%Y-%m-%d")

            # Analyze data quality
            total_meetings = len(meeting_history)
            meetings_with_summaries = sum(1 for m in meeting_history if m.get('summary'))

            # Get last 3 meetings for recent activity
            last_3_meetings = meeting_history[-3:] if len(meeting_history) >= 3 else meeting_history
            # Get last 10 meetings for comprehensive analysis
            recent_meetings = meeting_history[-10:] if len(meeting_history) >= 10 else meeting_history

            # Extract all action items and decisions from recent meetings
            all_action_items = []
            all_decisions = []
            all_key_points = []

            # Track action items with meeting context
            action_items_with_context = []
            decisions_with_context = []

            for meeting in recent_meetings:
                meeting_date = meeting.get('date', 'Unknown date')
                meeting_id = meeting.get('meeting_id', 'Unknown')

                # Add meeting context to action items
                for item in meeting.get('action_items', []):
                    item_with_context = item.copy() if isinstance(item, dict) else {'text': str(item)}
                    item_with_context['meeting_date'] = meeting_date
                    item_with_context['meeting_id'] = meeting_id
                    action_items_with_context.append(item_with_context)
                    all_action_items.append(item)

                # Add meeting context to decisions
                for decision in meeting.get('decisions', []):
                    decision_with_context = decision.copy() if isinstance(decision, dict) else {'text': str(decision)}
                    decision_with_context['meeting_date'] = meeting_date
                    decision_with_context['meeting_id'] = meeting_id
                    decisions_with_context.append(decision_with_context)
                    all_decisions.append(decision)

                all_key_points.extend(meeting.get('key_topics', []))

            # Calculate confidence based on data quality
            confidence_score = 0
            if total_meetings >= 5:
                confidence_score += 30
            elif total_meetings >= 2:
                confidence_score += 15

            if meetings_with_summaries >= 3:
                confidence_score += 30
            elif meetings_with_summaries >= 1:
                confidence_score += 15

            if len(all_action_items) >= 5:
                confidence_score += 40
            elif len(all_action_items) >= 2:
                confidence_score += 20

            # Determine confidence level
            if confidence_score >= 70:
                confidence = "HIGH"
                conf_explanation = f"Based on {total_meetings} meetings with {len(all_action_items)} action items."
            elif confidence_score >= 40:
                confidence = "MEDIUM"
                conf_explanation = f"Limited data: {total_meetings} meetings, {len(all_action_items)} action items. May miss some context."
            else:
                confidence = "LOW"
                conf_explanation = f"Insufficient data: Only {total_meetings} meetings recorded. Status check may be incomplete."

            # Prepare comprehensive meeting summaries for last 3 meetings
            last_3_summaries = []
            for i, meeting in enumerate(reversed(last_3_meetings), 1):
                meeting_date = meeting.get('date', 'Unknown')
                meeting_summary = meeting.get('summary', 'No summary available')[:300]  # Truncate long summaries
                last_3_summaries.append({
                    'number': i,
                    'date': meeting_date,
                    'summary': meeting_summary,
                    'action_count': len(meeting.get('action_items', [])),
                    'decision_count': len(meeting.get('decisions', []))
                })

            # Generate comprehensive status report using AI
            prompt = f"""You are a PROJECT MANAGER analyzing meeting history.

🚨 CRITICAL: CURRENT DATE & TIME 🚨
CURRENT DATE/TIME: {current_date_formatted}
TODAY'S DATE: {current_date_simple}

USE THIS DATE FOR ALL CALCULATIONS:
- "2 days ago" means relative to {current_date_simple}
- "yesterday" = {yesterday_date}
- "in 2 days" means relative to {current_date_simple}
- When showing "days until deadline", calculate from TODAY

TIMEZONE REQUIREMENT (CRITICAL):
- User timezone: {Config.USER_TIMEZONE}
- ALL times MUST include the timezone abbreviation
- Use 12-hour format: "2:30 PM {Config.USER_TIMEZONE}" NOT "14:30" or "2:30 PM"
- Format: "Meeting at 1:23 PM {Config.USER_TIMEZONE}" or "Deadline 5:00 PM {Config.USER_TIMEZONE}"

RELATIVE TIME CONTEXT (REQUIRED):
- Include relative time for all dates: "Meeting 2/15 (yesterday) at 1:23 PM {Config.USER_TIMEZONE}"
- For deadlines: "Feb 18 (in 2 days) at 5:00 PM {Config.USER_TIMEZONE}"
- For past items: "Last discussed 2/13 (3 days ago)"
- Calculate relative days from TODAY ({current_date_simple})

🚨 CRITICAL: ACCURACY OVER ASSUMPTIONS 🚨
- ONLY state facts EXPLICITLY mentioned in the meeting data
- NEVER infer or assume project status/phase unless clearly stated
- Mark ALL inferences as [INFERRED] vs [STATED]
- Include specific meeting references for EVERY fact
- If uncertain, write "UNCLEAR - needs clarification"
- Say "I don't know" rather than guess
- DO NOT HALLUCINATE facts not in the data

CONFIDENCE LEVELS (use for all major statements):
- [HIGH] = Explicitly stated in meeting transcript
- [MEDIUM] = Implied from context, not directly stated
- [LOW] = Assumption/inference, may need verification
- [UNCLEAR] = Not mentioned or ambiguous

DATA AVAILABLE:
- Total meetings: {total_meetings}
- Meetings analyzed: {len(recent_meetings)}
- Action items: {len(all_action_items)}
- Decisions: {len(all_decisions)}
- Key topics: {len(all_key_points)}

LAST 3 MEETINGS SUMMARY:
{json.dumps(last_3_summaries, indent=2)}

ALL ACTION ITEMS WITH MEETING DATES:
{json.dumps(action_items_with_context, indent=2)}

ALL DECISIONS WITH MEETING DATES:
{json.dumps(decisions_with_context, indent=2)}

KEY DISCUSSION TOPICS:
{json.dumps(all_key_points, indent=2)}

Generate a PROJECT MANAGEMENT STATUS REPORT with these EXACT sections:

═══════════════════════════════════════════════════════════
EXECUTIVE SUMMARY:
═══════════════════════════════════════════════════════════
(2-3 sentences: Current project state based ONLY on what was STATED in meetings)
CRITICAL: Include confidence level for project phase:
- If phase explicitly stated: "[HIGH] Project phase: Testing (stated in 2/15 meeting)"
- If phase unclear: "[UNCLEAR] Project phase not explicitly discussed in recent meetings"
- If inferring: "[LOW - INFERRED] Project appears to be in X phase based on Y discussion"

DO NOT STATE: "System is live" unless explicitly confirmed in a meeting
DO NOT ASSUME: Go-live status, launch dates, or phases without clear evidence


═══════════════════════════════════════════════════════════
MY ACTION ITEMS:
═══════════════════════════════════════════════════════════
ONLY list items EXPLICITLY mentioned in action items data.
Group by urgency:
[URGENT] items - flag ONLY if explicitly marked urgent, blocking, or time-sensitive in data
[NORMAL] items - all other action items

Format: "- [URGENT/NORMAL] Task description (Meeting 2/15 3:30pm)"
MUST include specific meeting date/time for each item
If no clear owner in data, flag as "[NO OWNER]"
DO NOT create action items not in the data


═══════════════════════════════════════════════════════════
WAITING ON OTHERS:
═══════════════════════════════════════════════════════════
List items assigned to other people/teams with:
- Who: Task description (requested MM/DD)


═══════════════════════════════════════════════════════════
UPCOMING DEADLINES & DATES:
═══════════════════════════════════════════════════════════
ONLY list dates EXPLICITLY mentioned in meeting data:
- MM/DD: What's due/happening [HIGH - stated in Meeting 2/XX]
If date was implied but not stated: "[MEDIUM - implied from discussion in Meeting 2/XX]"
Flag if overdue or coming up in next 2 weeks (based on report generation date)
If NO dates mentioned, write: "No specific dates or deadlines mentioned in recent meetings"
DO NOT infer dates not explicitly stated


═══════════════════════════════════════════════════════════
RECENT DECISIONS (Last 3 Meetings):
═══════════════════════════════════════════════════════════
Key decisions made:
- Decision description (MM/DD meeting)


═══════════════════════════════════════════════════════════
BLOCKERS & RISKS:
═══════════════════════════════════════════════════════════
ONLY list blockers/risks EXPLICITLY mentioned or clearly implied:
- Blocker/risk description [confidence level] (Meeting reference)

Examples:
"- Waiting on McKesson training dates [HIGH - explicitly stated as blocking in 2/13 meeting]"
"- Budget approval pending [MEDIUM - mentioned in 2/10, 2/12 meetings, blocking inference]"

If NO blockers mentioned: "No explicit blockers identified in recent meetings"
DO NOT assume blockers from absence of updates


═══════════════════════════════════════════════════════════
WHAT'S NEXT - SPECIFIC ACTIONS:
═══════════════════════════════════════════════════════════
Based ONLY on action items and discussions in meeting data:
- [ ] Action derived from open action items (Meeting reference)
- [ ] Follow-up based on "waiting on" items (Meeting reference)

Mark as [SUGGESTED] if inferring next step not explicitly stated
Examples:
"- [ ] Follow up with McKesson on dates [HIGH - action item from 2/13]"
"- [ ] [SUGGESTED] Schedule check-in meeting [LOW - inferred from lack of updates]"

If no clear next steps in data: "Next steps not explicitly defined in recent meetings"


═══════════════════════════════════════════════════════════
KEY METRICS:
═══════════════════════════════════════════════════════════
- Open action items: X (from action items data)
- Meetings analyzed: X (from meeting count)
- Decisions made (last 3 meetings): X
- Trend assessment:
  * Use [HIGH] for clearly evident trends from data
  * Use [MEDIUM] for inferred trends with some evidence
  * Use [LOW] for weak inferences
  * Examples:
    - "Making progress [MEDIUM - 5 of 8 items completed based on discussion]"
    - "Status unclear [LOW - insufficient updates in recent meetings]"
    - "Blocked [HIGH - McKesson dependency explicitly stated as blocker]"


CRITICAL INSTRUCTIONS - ACCURACY REQUIREMENTS:
- Use EXACT section headers with separators (═══)
- ONLY state facts explicitly mentioned in meeting data
- Include meeting reference for EVERY fact: "(Meeting 2/15 12:30pm)" or "(from 2/15 meeting)"
- Use confidence tags: [HIGH], [MEDIUM], [LOW], [UNCLEAR]
- Mark inferences: "[INFERRED from discussion about X]"
- If project status/phase unclear, say so explicitly
- Be SPECIFIC with meeting dates, names, deadlines
- Flag URGENT items with [URGENT]
- If section has no data, write "None identified" or "Not discussed in meetings"
- DO NOT hallucinate facts - better to say "Unknown" or "Unclear"
- DO NOT assume current status unless explicitly stated
- Prioritize ACCURACY over completeness
- Format for easy scanning (bullet points, clear structure)

EXAMPLES OF PROPER DATE/TIME FORMATTING:
✓ GOOD: "Meeting 2/15 (yesterday) at 1:23 PM {Config.USER_TIMEZONE}"
✓ GOOD: "Deadline Feb 18 (in 2 days) at 5:00 PM {Config.USER_TIMEZONE}"
✓ GOOD: "Last discussed 2/13 (3 days ago)"
✗ BAD: "Meeting at 13:23" (no timezone, 24-hour format)
✗ BAD: "Meeting at 1:23 PM" (no timezone)
✗ BAD: "Follow-up by 2/18" (no relative time, no timezone)

EXAMPLES OF PROPER GROUNDING:
✓ GOOD: "Launch: Week of Feb 24 [HIGH - stated by [MANAGER] in 2/15 meeting at 2:30 PM {Config.USER_TIMEZONE}]"
✓ GOOD: "[UNCLEAR] Current go-live status - not discussed in recent meetings"
✓ GOOD: "Training mentioned [MEDIUM - implied from action item in 2/13 meeting]"
✗ BAD: "System is currently live" (not stated anywhere)
✗ BAD: "Project in operational phase" (assumption)
✗ BAD: "Launch successful" (not confirmed)"""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=3000,  # Increased for comprehensive report
                temperature=0.3,  # Lower for more consistent formatting
                system=Config.PILOT_SYSTEM_CONTEXT,
                messages=[{"role": "user", "content": prompt}]
            )

            status_report = response.content[0].text

            logger.info("Comprehensive status check generated successfully")

            return {
                'status_report': status_report,
                'confidence': confidence,
                'confidence_explanation': conf_explanation,
                'generated_at': current_date_formatted,  # Include generation timestamp
                'generated_date': current_date_simple,
                'data_quality': {
                    'total_meetings': total_meetings,
                    'meetings_with_summaries': meetings_with_summaries,
                    'action_items_count': len(all_action_items),
                    'decisions_count': len(all_decisions),
                    'confidence_score': confidence_score,
                    'last_3_meetings': len(last_3_meetings),
                    'recent_meetings': len(recent_meetings)
                }
            }

        except Exception as e:
            logger.error(f"Error generating status check: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status_report': f"Error generating status check: {str(e)}",
                'confidence': 'LOW',
                'confidence_explanation': 'Failed to analyze meeting data',
                'data_quality': {}
            }

    def query_meetings(self, question: str, meeting_history: List[Dict]) -> Dict:
        """
        Answer a specific question by searching meeting history.

        Args:
            question: User's question about meetings
            meeting_history: List of meeting data from persistent memory

        Returns:
            Dict with:
                'answer': str (the answer)
                'confidence': str ('HIGH', 'MEDIUM', 'LOW')
                'sources': List[str] (meeting IDs where info was found)
        """
        try:
            logger.info(f"Querying meetings: {question}")

            # Get recent meetings (last 15 for broader context)
            recent_meetings = meeting_history[-15:] if len(meeting_history) > 15 else meeting_history

            # Build context from meeting summaries
            context_parts = []
            meeting_sources = []

            for meeting in recent_meetings:
                meeting_id = meeting.get('meeting_id', 'Unknown')
                date = meeting.get('date', 'Unknown date')
                summary = meeting.get('summary', '')

                if summary:
                    context_parts.append(f"\n--- MEETING {meeting_id} ({date}) ---\n{summary}\n")
                    meeting_sources.append((meeting_id, date))

            full_context = "\n".join(context_parts)

            # Calculate confidence based on data availability
            if not context_parts:
                return {
                    'answer': "No meeting data available to answer this question.",
                    'confidence': 'LOW',
                    'sources': []
                }

            confidence = "HIGH" if len(context_parts) >= 5 else "MEDIUM" if len(context_parts) >= 2 else "LOW"

            # Query AI with meeting context
            prompt = f"""You are answering a question about past project meetings.

MEETING HISTORY:
{full_context}

USER QUESTION: {question}

Instructions:
1. Search through the meeting summaries above for information relevant to the question
2. Provide a clear, specific answer based ONLY on information found in the meetings
3. If the information is not in the meetings, say "I don't see that information in the recorded meetings"
4. Reference which meeting(s) the information came from (by meeting ID and date)
5. Quote specific details (dates, times, names) when available
6. Keep the answer concise (2-4 sentences)

Answer format:
[Your answer with specific details]

Source: Meeting [ID] on [date]"""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=800,
                temperature=0.3,
                system=Config.PILOT_SYSTEM_CONTEXT,
                messages=[{"role": "user", "content": prompt}]
            )

            answer = response.content[0].text

            logger.info("Query answered successfully")

            return {
                'answer': answer,
                'confidence': confidence,
                'sources': [f"{mid} ({date})" for mid, date in meeting_sources]
            }

        except Exception as e:
            logger.error(f"Error querying meetings: {e}")
            return {
                'answer': f"Error searching meetings: {str(e)}",
                'confidence': 'LOW',
                'sources': []
            }


def test_analyzer():
    """Test AI analyzer functionality."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing AI analyzer module...")

    # Check for API key
    if not Config.ANTHROPIC_API_KEY or Config.ANTHROPIC_API_KEY == 'sk-ant-...':
        print("✗ Error: ANTHROPIC_API_KEY not set in .env file")
        return

    try:
        analyzer = MeetingAnalyzer()
        print("✓ Analyzer initialized\n")

        # Test with sample transcription
        sample_text = """
        John: Okay team, let's discuss the Q1 roadmap. Sarah, can you give us an update on the API project?

        Sarah: Sure! We've completed the authentication module and we're on track to finish the REST endpoints by next Friday. However, we need to decide on the rate limiting approach.

        Mike: I think we should go with a token bucket algorithm. It's more flexible than fixed window.

        John: Agreed. Let's implement token bucket. Sarah, can you update the technical spec with that decision?

        Sarah: Will do. I'll have the updated spec ready by tomorrow.

        Mike: I'll also need to schedule a security review meeting for next week. John, can you join?

        John: Yes, put me down for that. What day works best?
        """

        print("Analyzing sample transcription...")
        result = analyzer.analyze_chunk(sample_text)

        if result:
            print("\n✓ Analysis successful!\n")

            if result['action_items']:
                print("Action Items:")
                for item in result['action_items']:
                    assignee = f" → {item['assignee']}" if item['assignee'] else ""
                    print(f"  - {item['item']}{assignee}")

            if result['decisions']:
                print("\nDecisions:")
                for decision in result['decisions']:
                    print(f"  - {decision}")

            if result['key_points']:
                print("\nKey Points:")
                for point in result['key_points']:
                    print(f"  - {point}")

            if result['participants']:
                print("\nParticipants:")
                print(f"  {', '.join(result['participants'])}")

            # Test summary generation
            print("\n" + "=" * 60)
            print("Generating meeting summary...")
            summary = analyzer.generate_summary()
            print("\n" + summary)

        else:
            print("✗ Analysis failed")

    except Exception as e:
        print(f"\n✗ Error: {e}")


if __name__ == '__main__':
    test_analyzer()
