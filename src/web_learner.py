"""Web learning module to load and serve domain knowledge from pre-gathered sources."""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from anthropic import Anthropic

from .config import Config

logger = logging.getLogger(__name__)


class WebLearner:
    """Loads and serves pre-gathered domain knowledge for use in queries."""

    def __init__(self, memory_dir: Optional[Path] = None):
        """
        Initialize web learner.

        Args:
            memory_dir: Directory to store learned knowledge (default: meetings/)
        """
        self.memory_dir = memory_dir or Config.MEETINGS_DIR
        _slug = Config.PRODUCT_NAME.lower().replace(' ', '_') if Config.PRODUCT_NAME else "product"
        self.knowledge_file = self.memory_dir / f"{_slug}_web_knowledge.json"
        self.client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.model = "claude-sonnet-4-5-20250929"

        self.knowledge = {
            'last_updated': None,
            'sources': [],
            'topics': {},
            'raw_content': []
        }

        self.load_knowledge()

    def load_knowledge(self):
        """Load existing knowledge from disk."""
        try:
            if self.knowledge_file.exists():
                with open(self.knowledge_file, 'r', encoding='utf-8') as f:
                    self.knowledge = json.load(f)
                logger.info(f"Loaded knowledge: {len(self.knowledge['sources'])} sources")
            else:
                logger.info("No existing web knowledge, starting fresh")
        except Exception as e:
            logger.error(f"Error loading knowledge: {e}")

    def save_knowledge(self):
        """Save knowledge to disk."""
        try:
            self.knowledge['last_updated'] = datetime.now().isoformat()
            with open(self.knowledge_file, 'w', encoding='utf-8') as f:
                json.dump(self.knowledge, f, indent=2)
            logger.info("Knowledge saved to disk")
        except Exception as e:
            logger.error(f"Error saving knowledge: {e}")

    def learn_from_web(self, max_sources: int = 10) -> Dict:
        """
        Load the pre-gathered web knowledge about the configured product.

        Args:
            max_sources: Maximum number of sources to fetch (not used, kept for compatibility)

        Returns:
            Dict with learning results
        """
        _product = Config.PRODUCT_NAME or "product"
        logger.info(f"Loading {_product} web knowledge...")

        results = {
            'sources_found': 0,
            'topics_learned': 0,
            'success': False,
            'summary': '',
            'sources_fetched': []
        }

        try:
            # Check if knowledge already exists
            if self.has_knowledge():
                logger.info("Web knowledge already loaded")
                results['sources_found'] = len(self.knowledge['sources'])
                results['topics_learned'] = len(self.knowledge['topics'])
                results['success'] = True
                results['summary'] = "Knowledge already available from previous web research"
                return results

            # If no knowledge exists, return message that manual research is needed
            results['success'] = False
            results['summary'] = "Web knowledge not yet gathered. Knowledge base files should be pre-loaded."
            logger.warning("No web knowledge found")
            return results

        except Exception as e:
            logger.error(f"Error loading web knowledge: {e}")
            results['success'] = False
            results['summary'] = f"Error: {str(e)}"
            return results

    def _extract_topics(self, content: str):
        """Extract and categorize topics from content."""
        # Simple topic extraction - could be enhanced with NLP
        topic_keywords = {
            'rems': ['REMS', 'Risk Evaluation', 'Mitigation Strategy'],
            'training': ['training', 'certification', 'education'],
            'insertion': ['insertion', 'placement', 'procedure'],
            'removal': ['removal', 'explantation'],
            'safety': ['safety', 'adverse', 'complications', 'risks'],
            'efficacy': ['efficacy', 'effectiveness', 'prevention'],
            'compliance': ['compliance', 'regulatory', 'FDA'],
            'providers': ['healthcare provider', 'physician', 'clinician'],
        }

        for topic, keywords in topic_keywords.items():
            if any(keyword.lower() in content.lower() for keyword in keywords):
                if topic not in self.knowledge['topics']:
                    self.knowledge['topics'][topic] = []

                # Store snippet related to this topic
                # Simple approach: find sentences containing keywords
                sentences = content.split('.')
                relevant_sentences = [
                    s.strip() for s in sentences
                    if any(kw.lower() in s.lower() for kw in keywords)
                ][:5]  # Top 5 relevant sentences

                if relevant_sentences:
                    self.knowledge['topics'][topic].extend(relevant_sentences)

    def get_knowledge_summary(self) -> str:
        """Get a summary of learned knowledge."""
        if not self.knowledge['sources']:
            return "No web knowledge learned yet. Run 'Learn from Web' first."

        lines = []
        _product = Config.PRODUCT_NAME or "Product"
        lines.append(f"{_product.upper()} WEB KNOWLEDGE BASE")
        lines.append("=" * 70)
        lines.append(f"Last Updated: {self.knowledge.get('last_updated', 'Never')}")
        lines.append(f"Sources: {len(self.knowledge['sources'])}")
        lines.append(f"Topics: {len(self.knowledge['topics'])}")
        lines.append("")

        if self.knowledge['topics']:
            lines.append("Topics Covered:")
            for topic in self.knowledge['topics'].keys():
                lines.append(f"  - {topic.upper()}")

        lines.append("")
        lines.append("Knowledge available for queries about:")
        lines.append(f"  • {Config.PRODUCT_NAME or 'Product'} information")
        lines.append("  • REMS program requirements")
        lines.append("  • Training and certification")
        lines.append("  • Clinical guidelines")
        lines.append("  • Safety and efficacy")
        lines.append("  • Provider requirements")
        lines.append("  • Regulatory compliance")

        return "\n".join(lines)

    def get_knowledge_for_query(self) -> str:
        """Get formatted knowledge for inclusion in query context."""
        if not self.knowledge['raw_content']:
            return ""

        # Return the most recent comprehensive content
        latest = self.knowledge['raw_content'][-1]

        context = f"""
=== {Config.PRODUCT_NAME.upper() if Config.PRODUCT_NAME else "PRODUCT"} KNOWLEDGE BASE ===
Source: {latest['source']}
Retrieved: {latest['date_retrieved']}

{latest['content']}

=== END KNOWLEDGE BASE ===
"""
        return context

    def has_knowledge(self) -> bool:
        """Check if we have learned knowledge available."""
        return len(self.knowledge['raw_content']) > 0


def test_web_learner():
    """Test web learner functionality."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing Web Learner...")
    _product = Config.PRODUCT_NAME or "product"
    print(f"This will load web knowledge about {_product}.\n")

    learner = WebLearner()

    # Check for existing knowledge
    if learner.has_knowledge():
        print("Existing knowledge found:")
        print(learner.get_knowledge_summary())
        print("\n" + "=" * 70 + "\n")

    # Learn from web
    print(f"Loading {_product} knowledge...")
    results = learner.learn_from_web()

    if results['success']:
        print("\n✓ Learning complete!")
        print(f"  Sources: {results['sources_found']}")
        print(f"  Topics: {results['topics_learned']}")
        print("\nSummary:")
        print(results['summary'])
        print("\n" + "=" * 70 + "\n")
        print(learner.get_knowledge_summary())
    else:
        print(f"\n✗ Learning failed: {results['summary']}")


if __name__ == '__main__':
    test_web_learner()
