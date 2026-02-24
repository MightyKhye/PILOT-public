"""Persistent memory system to remember all meetings and build context over time."""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

from .config import Config

logger = logging.getLogger(__name__)


class PersistentMemory:
    """Manages persistent storage of all meeting data across sessions."""

    def __init__(self, memory_file: Optional[Path] = None):
        """
        Initialize persistent memory.

        Args:
            memory_file: Path to memory storage file (default: meetings/persistent_memory.json)
        """
        self.memory_file = memory_file or (Config.MEETINGS_DIR / "persistent_memory.json")
        self.memory_data = {
            'meetings': [],
            'participants': set(),
            'recurring_topics': [],
            'action_items_history': [],
            'decisions_history': [],
            'documents': []  # Uploaded REMS documents
        }
        self.load()

    def load(self):
        """
        Load memory from disk with corruption recovery.

        CORRUPTION RECOVERY:
        1. Try loading main file
        2. If corrupted, try loading .bak backup
        3. If both fail, start fresh
        """
        try:
            if self.memory_file.exists():
                try:
                    # Try loading main file
                    with open(self.memory_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # Validate structure
                    if 'meetings' not in data:
                        raise ValueError("Invalid memory data - missing 'meetings' key")

                    # Convert sets back from lists
                    if 'participants' in data:
                        data['participants'] = set(data['participants'])

                    self.memory_data.update(data)
                    logger.info(f"Loaded memory: {len(self.memory_data['meetings'])} meetings")

                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Memory file corrupted: {e}")

                    # Try loading from backup
                    backup_file = Path(str(self.memory_file) + '.bak')
                    if backup_file.exists():
                        logger.info("Attempting to recover from backup...")
                        try:
                            with open(backup_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)

                            # Validate structure
                            if 'meetings' not in data:
                                raise ValueError("Invalid backup data - missing 'meetings' key")

                            # Convert sets back from lists
                            if 'participants' in data:
                                data['participants'] = set(data['participants'])

                            self.memory_data.update(data)
                            logger.info(f"Recovered from backup: {len(self.memory_data['meetings'])} meetings")

                            # Restore backup as main file
                            import shutil
                            shutil.copy2(backup_file, self.memory_file)
                            logger.info("Restored backup as main file")

                        except Exception as backup_error:
                            logger.error(f"Backup also corrupted: {backup_error}")
                            logger.warning("Starting with fresh memory - previous data could not be recovered")
                    else:
                        logger.warning("No backup file available - starting with fresh memory")
            else:
                logger.info("No existing memory file, starting fresh")

        except Exception as e:
            logger.error(f"Unexpected error loading memory: {e}")
            logger.warning("Starting with fresh memory")

    def save(self):
        """
        Save memory to disk with atomic writes to prevent corruption.

        CORRUPTION PREVENTION:
        1. Write to .tmp file
        2. Verify JSON is valid
        3. Backup existing file to .bak
        4. Atomic rename .tmp to .json
        """
        try:
            # Convert sets to lists for JSON serialization
            save_data = self.memory_data.copy()
            if 'participants' in save_data:
                save_data['participants'] = list(save_data['participants'])

            # STEP 1: Write to temporary file
            tmp_file = Path(str(self.memory_file) + '.tmp')
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2)

            # STEP 2: Verify JSON is valid by reading it back
            with open(tmp_file, 'r', encoding='utf-8') as f:
                verification_data = json.load(f)
                # Quick sanity check
                if 'meetings' not in verification_data:
                    raise ValueError("Invalid memory data structure - missing 'meetings' key")

            # STEP 3: Backup existing file (if it exists)
            if self.memory_file.exists():
                backup_file = Path(str(self.memory_file) + '.bak')
                import shutil
                shutil.copy2(self.memory_file, backup_file)
                logger.debug(f"Created backup: {backup_file}")

            # STEP 4: Atomic rename (atomic on most filesystems)
            tmp_file.replace(self.memory_file)

            logger.info("Memory saved to disk (atomic write)")

        except Exception as e:
            logger.error(f"Error saving memory: {e}")
            # Clean up temp file if it exists
            tmp_file = Path(str(self.memory_file) + '.tmp')
            if tmp_file.exists():
                tmp_file.unlink()
            raise  # Re-raise to alert caller

    def add_meeting(self, meeting_data: Dict):
        """
        Add a completed meeting to memory.

        Args:
            meeting_data: Meeting data including transcriptions, analyses, summary
        """
        meeting_record = {
            'meeting_id': meeting_data.get('meeting_id'),
            'date': meeting_data.get('start_time'),
            'duration': meeting_data.get('duration'),
            'summary': meeting_data.get('summary', ''),
            'action_items': [],
            'decisions': [],
            'key_topics': []
        }

        # Extract key information from analyses
        for analysis in meeting_data.get('analyses', []):
            analysis_data = analysis.get('analysis', {})

            # Store action items
            for item in analysis_data.get('action_items', []):
                meeting_record['action_items'].append(item)
                self.memory_data['action_items_history'].append({
                    'item': item,
                    'meeting_id': meeting_data.get('meeting_id'),
                    'date': meeting_data.get('start_time')
                })

            # Store decisions
            for decision in analysis_data.get('decisions', []):
                meeting_record['decisions'].append(decision)
                self.memory_data['decisions_history'].append({
                    'decision': decision,
                    'meeting_id': meeting_data.get('meeting_id'),
                    'date': meeting_data.get('start_time')
                })

            # Store key points
            meeting_record['key_topics'].extend(analysis_data.get('key_points', []))

            # Track participants
            for participant in analysis_data.get('participants', []):
                self.memory_data['participants'].add(participant)

        self.memory_data['meetings'].append(meeting_record)
        self.save()
        logger.info(f"Added meeting {meeting_data.get('meeting_id')} to persistent memory")

    def get_context_summary(self, max_meetings: int = 5) -> str:
        """
        Generate a context summary from recent meetings.

        Args:
            max_meetings: Number of recent meetings to include

        Returns:
            Formatted context string for AI analysis
        """
        if not self.memory_data['meetings']:
            return "No previous meeting history."

        recent_meetings = self.memory_data['meetings'][-max_meetings:]

        context_parts = []
        context_parts.append(f"HISTORICAL CONTEXT ({len(self.memory_data['meetings'])} total meetings)")
        context_parts.append("")

        # Recent meetings summary
        context_parts.append(f"Recent {len(recent_meetings)} meetings:")
        for meeting in recent_meetings:
            context_parts.append(f"  - {meeting.get('date', 'Unknown date')}: {len(meeting.get('action_items', []))} action items, {len(meeting.get('decisions', []))} decisions")

        # Recurring participants
        if self.memory_data['participants']:
            context_parts.append("")
            context_parts.append(f"Frequent participants: {', '.join(list(self.memory_data['participants'])[:10])}")

        # Recent action items
        recent_actions = self.memory_data['action_items_history'][-10:]
        if recent_actions:
            context_parts.append("")
            context_parts.append("Recent action items:")
            for action in recent_actions:
                item_text = action['item'].get('item', action['item']) if isinstance(action['item'], dict) else action['item']
                context_parts.append(f"  - {item_text}")

        # Recent decisions
        recent_decisions = self.memory_data['decisions_history'][-5:]
        if recent_decisions:
            context_parts.append("")
            context_parts.append("Recent decisions:")
            for decision in recent_decisions:
                dec_text = decision['decision'].get('decision', decision['decision']) if isinstance(decision['decision'], dict) else decision['decision']
                context_parts.append(f"  - {dec_text}")

        return "\n".join(context_parts)

    def add_document(self, doc_path: Path, doc_type: str = "REMS") -> str:
        """
        Add a reference document to memory.

        Args:
            doc_path: Path to document
            doc_type: Type of document (REMS, training, etc.)

        Returns:
            Status: 'added', 'duplicate', or 'updated'
        """
        # Check for duplicates by filename
        existing_doc = None
        for idx, doc in enumerate(self.memory_data['documents']):
            if doc['filename'] == doc_path.name:
                existing_doc = (idx, doc)
                break

        if existing_doc:
            idx, doc = existing_doc
            # Check if path is the same
            if doc['path'] == str(doc_path):
                logger.info(f"Duplicate skipped: {doc_path.name}")
                return 'duplicate'
            else:
                # Same filename, different path - update it
                self.memory_data['documents'][idx] = {
                    'path': str(doc_path),
                    'filename': doc_path.name,
                    'type': doc_type,
                    'added': datetime.now().isoformat()
                }
                self.save()
                logger.info(f"Updated document: {doc_path.name}")
                return 'updated'
        else:
            # New document
            doc_record = {
                'path': str(doc_path),
                'filename': doc_path.name,
                'type': doc_type,
                'added': datetime.now().isoformat()
            }
            self.memory_data['documents'].append(doc_record)
            self.save()
            logger.info(f"Added document: {doc_path.name}")
            return 'added'

    def get_documents(self) -> List[Dict]:
        """Get list of all uploaded documents."""
        return self.memory_data['documents']

    def search_history(self, query: str) -> List[Dict]:
        """
        Search through meeting history for relevant information.

        Args:
            query: Search query

        Returns:
            List of relevant meetings
        """
        query_lower = query.lower()
        relevant_meetings = []

        for meeting in self.memory_data['meetings']:
            # Search in summary, action items, decisions, key topics
            if (query_lower in str(meeting.get('summary', '')).lower() or
                any(query_lower in str(item).lower() for item in meeting.get('action_items', [])) or
                any(query_lower in str(dec).lower() for dec in meeting.get('decisions', [])) or
                any(query_lower in str(topic).lower() for topic in meeting.get('key_topics', []))):
                relevant_meetings.append(meeting)

        return relevant_meetings
