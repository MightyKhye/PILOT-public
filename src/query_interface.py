"""Live query interface to ask questions about documents and meeting history."""

import logging
from pathlib import Path
from typing import Optional, List
from anthropic import Anthropic

from .config import Config
from .persistent_memory import PersistentMemory
from .web_learner import WebLearner

logger = logging.getLogger(__name__)


class QueryInterface:
    """Interface to query meeting history and uploaded documents."""

    def __init__(self, memory: Optional[PersistentMemory] = None):
        """
        Initialize query interface.

        Args:
            memory: PersistentMemory instance (creates new if not provided)
        """
        self.memory = memory or PersistentMemory()
        self.web_learner = WebLearner()
        self.client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.model = "claude-sonnet-4-5-20250929"

    def query(self, question: str, include_documents: bool = True) -> str:
        """
        Ask a question about REMS or meeting history.

        Args:
            question: User's question
            include_documents: Whether to include uploaded REMS documents in context

        Returns:
            Claude's answer
        """
        try:
            logger.info(f"Processing query: {question}")

            # Build context from meeting history
            context_parts = []

            # Add web-learned product knowledge first (foundational context)
            if self.web_learner.has_knowledge():
                context_parts.append(self.web_learner.get_knowledge_for_query())
                context_parts.append("")

            # Add meeting history context
            context_parts.append("=== MEETING HISTORY ===")
            context_parts.append(self.memory.get_context_summary(max_meetings=10))
            context_parts.append("")

            # Search for relevant meetings
            relevant_meetings = self.memory.search_history(question)
            if relevant_meetings:
                context_parts.append("=== RELEVANT PAST MEETINGS ===")
                for meeting in relevant_meetings[:3]:  # Top 3 most relevant
                    context_parts.append(f"\nMeeting: {meeting.get('date', 'Unknown')}")
                    context_parts.append(f"Summary: {meeting.get('summary', 'No summary')[:500]}")
                    if meeting.get('action_items'):
                        context_parts.append("Action items:")
                        for item in meeting.get('action_items', [])[:3]:
                            item_text = item.get('item', item) if isinstance(item, dict) else item
                            context_parts.append(f"  - {item_text}")
                context_parts.append("")

            # Add uploaded documents context
            if include_documents:
                documents = self.memory.get_documents()
                if documents:
                    context_parts.append("=== AVAILABLE DOCUMENTS ===")
                    for doc in documents:
                        context_parts.append(f"  - {doc['filename']} ({doc['type']})")
                        # Try to read document content
                        try:
                            doc_path = Path(doc['path'])
                            if doc_path.exists() and doc_path.suffix in ['.txt', '.md']:
                                with open(doc_path, 'r', encoding='utf-8') as f:
                                    content = f.read()[:5000]  # First 5000 chars
                                    context_parts.append(f"\nContent excerpt from {doc['filename']}:")
                                    context_parts.append(content)
                        except Exception as e:
                            logger.warning(f"Could not read document {doc['filename']}: {e}")
                    context_parts.append("")

            context = "\n".join(context_parts)

            # Create prompt for Claude
            _domain = f"{Config.PRODUCT_NAME} " if Config.PRODUCT_NAME else ""
            prompt = f"""You are an expert assistant with access to {_domain}meeting history and supporting documents.

{context}

User question: {question}

Provide a clear, accurate answer based on the available context. If the answer isn't in the provided context, say so. Be specific and reference meetings or documents when relevant.

Answer:"""

            # Query Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )

            answer = response.content[0].text
            logger.info("Query answered successfully")
            return answer

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return f"Error processing query: {str(e)}"

    def add_rems_document(self, doc_path: Path) -> str:
        """
        Add a supporting document to the knowledge base.

        Args:
            doc_path: Path to document file

        Returns:
            Status: 'added', 'duplicate', 'updated', or 'error'
        """
        try:
            if not doc_path.exists():
                logger.error(f"Document not found: {doc_path}")
                return 'error'

            status = self.memory.add_document(doc_path, doc_type="document")
            logger.info(f"Document {status}: {doc_path.name}")
            return status

        except Exception as e:
            logger.error(f"Error adding document: {e}")
            return 'error'

    def list_documents(self) -> List[str]:
        """Get list of all uploaded document names."""
        docs = self.memory.get_documents()
        return [doc['filename'] for doc in docs]

    def get_meeting_summary(self, meeting_id: Optional[str] = None) -> str:
        """
        Get summary of a specific meeting or recent meetings.

        Args:
            meeting_id: Specific meeting ID (None for recent meetings)

        Returns:
            Meeting summary text
        """
        meetings = self.memory.memory_data['meetings']

        if not meetings:
            return "No meetings recorded yet."

        if meeting_id:
            # Find specific meeting
            for meeting in meetings:
                if meeting.get('meeting_id') == meeting_id:
                    return self._format_meeting_summary(meeting)
            return f"Meeting {meeting_id} not found."
        else:
            # Show recent meetings
            recent = meetings[-5:]
            summaries = []
            for meeting in recent:
                summaries.append(self._format_meeting_summary(meeting))
            return "\n\n".join(summaries)

    def learn_product_from_web(self) -> Dict:
        """
        Load pre-gathered web knowledge about the configured product.

        Returns:
            Dict with learning results
        """
        _product = Config.PRODUCT_NAME or "product"
        logger.info(f"Initiating web learning about {_product}...")
        return self.web_learner.learn_from_web()

    def get_web_knowledge_status(self) -> str:
        """Get status of web-learned knowledge."""
        return self.web_learner.get_knowledge_summary()

    def has_web_knowledge(self) -> bool:
        """Check if web knowledge is available."""
        return self.web_learner.has_knowledge()

    def _format_meeting_summary(self, meeting: dict) -> str:
        """Format a meeting record for display."""
        lines = []
        lines.append(f"Meeting: {meeting.get('meeting_id', 'Unknown')}")
        lines.append(f"Date: {meeting.get('date', 'Unknown')}")
        lines.append(f"Duration: {meeting.get('duration', 'Unknown')}")

        if meeting.get('action_items'):
            lines.append(f"\nAction Items ({len(meeting['action_items'])}):")
            for item in meeting['action_items'][:5]:
                item_text = item.get('item', item) if isinstance(item, dict) else item
                lines.append(f"  - {item_text}")

        if meeting.get('decisions'):
            lines.append(f"\nDecisions ({len(meeting['decisions'])}):")
            for dec in meeting['decisions'][:3]:
                dec_text = dec.get('decision', dec) if isinstance(dec, dict) else dec
                lines.append(f"  - {dec_text}")

        return "\n".join(lines)


def test_query_interface():
    """Test query interface."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing Query Interface...")

    query_interface = QueryInterface()

    # Test questions
    test_questions = [
        "What are the recent action items about training?",
        "What decisions have been made regarding virtual training?",
        "Who are the frequent meeting participants?",
    ]

    for question in test_questions:
        print(f"\nQuestion: {question}")
        print("-" * 70)
        answer = query_interface.query(question)
        print(answer)
        print()


if __name__ == '__main__':
    test_query_interface()
