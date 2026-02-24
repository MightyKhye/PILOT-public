"""Windows notification module for meeting insights."""

import logging
import queue
import threading
import time
from typing import Optional, Dict, List
from winotify import Notification, audio

logger = logging.getLogger(__name__)


class MeetingNotifier:
    """Manages Windows toast notifications for meeting insights."""

    def __init__(self):
        """Initialize notifier."""
        self.notification_queue = queue.Queue()
        self.notification_thread: Optional[threading.Thread] = None
        self.running = False

        # App identifier for notifications
        self.app_id = "Pilot"
        self.icon_path = None  # Optional: path to app icon

    def start(self):
        """Start notification worker thread."""
        if self.running:
            logger.warning("Notifier already running")
            return

        self.running = True
        self.notification_thread = threading.Thread(
            target=self._notification_loop,
            daemon=True
        )
        self.notification_thread.start()
        logger.info("Notification system started")

    def stop(self):
        """Stop notification worker thread."""
        if not self.running:
            return

        self.running = False

        if self.notification_thread:
            self.notification_thread.join(timeout=5)

        logger.info("Notification system stopped")

    def _notification_loop(self):
        """Process notifications from queue."""
        while self.running:
            try:
                # Get notification with timeout to allow checking running flag
                notification_data = self.notification_queue.get(timeout=1)

                if notification_data:
                    self._show_notification(notification_data)

                    # Small delay to avoid notification spam
                    time.sleep(0.5)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in notification loop: {e}")
                time.sleep(1)

    def _show_notification(self, data: Dict):
        """
        Show a Windows toast notification.

        Args:
            data: Notification data dict with 'title', 'message', 'duration'
        """
        try:
            toast = Notification(
                app_id=self.app_id,
                title=data['title'],
                msg=data['message'],
                duration='short',  # Always use short duration (less intrusive)
                icon=self.icon_path if self.icon_path else ""
            )

            # Set audio (optional)
            if data.get('sound', True):
                toast.set_audio(audio.Default, loop=False)

            # Add action buttons if provided
            if 'actions' in data:
                for action in data['actions']:
                    toast.add_actions(
                        label=action.get('label', 'Open'),
                        launch=action.get('launch', '')
                    )

            # Show notification
            toast.show()

            logger.info(f"Notification shown: {data['title']}")

        except Exception as e:
            logger.error(f"Failed to show notification: {e}")

    def notify_action_item(self, item: str, assignee: Optional[str] = None):
        """
        Show notification for a new action item.

        Args:
            item: Action item description
            assignee: Person assigned (optional)
        """
        title = "New Action Item"

        if assignee:
            message = f"{assignee}: {item}"
        else:
            message = item

        self.notification_queue.put({
            'title': title,
            'message': message,
            'duration': 'long',
            'sound': True
        })

        logger.info(f"Queued action item notification: {item}")

    def notify_decision(self, decision: str):
        """
        Show notification for a new decision.

        Args:
            decision: Decision description
        """
        title = "Decision Made"
        message = decision

        self.notification_queue.put({
            'title': title,
            'message': message,
            'duration': 'long',
            'sound': True
        })

        logger.info(f"Queued decision notification: {decision}")

    def notify_key_point(self, point: str):
        """
        Show notification for a key discussion point.

        Args:
            point: Key point description
        """
        title = "Key Point"
        message = point

        self.notification_queue.put({
            'title': title,
            'message': message,
            'duration': 'short',
            'sound': False  # Less urgent than action items
        })

        logger.info(f"Queued key point notification: {point}")

    def notify_summary(self, summary: str, meeting_duration: Optional[str] = None):
        """
        Show notification for meeting summary.

        Args:
            summary: Brief summary text
            meeting_duration: Optional meeting duration string
        """
        title = "Meeting Summary Ready"

        if meeting_duration:
            message = f"Meeting duration: {meeting_duration}\n\n{summary[:150]}..."
        else:
            message = summary[:200] + "..." if len(summary) > 200 else summary

        self.notification_queue.put({
            'title': title,
            'message': message,
            'duration': 'long',
            'sound': True
        })

        logger.info("Queued summary notification")

    def notify_error(self, error: str):
        """
        Show error notification.

        Args:
            error: Error message
        """
        title = "Meeting Listener Error"
        message = error

        self.notification_queue.put({
            'title': title,
            'message': message,
            'duration': 'long',
            'sound': True
        })

        logger.info(f"Queued error notification: {error}")

    def notify_status(self, status: str):
        """
        Show status notification.

        Args:
            status: Status message
        """
        title = "Pilot"
        message = status

        self.notification_queue.put({
            'title': title,
            'message': message,
            'duration': 'short',
            'sound': False
        })

        logger.info(f"Queued status notification: {status}")

    def notify_batch(self, items: List[Dict]):
        """
        Queue multiple notifications from analysis results.

        Args:
            items: List of items from AI analysis
                   Each item should have 'type' and content
        """
        for item in items:
            item_type = item.get('type')

            if item_type == 'action_item':
                self.notify_action_item(
                    item.get('item', ''),
                    item.get('assignee')
                )
            elif item_type == 'decision':
                self.notify_decision(item.get('text', ''))
            elif item_type == 'key_point':
                self.notify_key_point(item.get('text', ''))

    def clear_queue(self):
        """Clear all pending notifications."""
        while not self.notification_queue.empty():
            try:
                self.notification_queue.get_nowait()
            except queue.Empty:
                break

        logger.info("Notification queue cleared")


def test_notifier():
    """Test notification functionality."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing Windows notification system...")
    print("You should see toast notifications appear.\n")

    notifier = MeetingNotifier()

    try:
        # Start notifier
        notifier.start()
        print("✓ Notifier started\n")

        # Test different notification types
        print("Sending test notifications...")

        print("1. Status notification")
        notifier.notify_status("Recording started")
        time.sleep(3)

        print("2. Action item notification")
        notifier.notify_action_item(
            "Update the technical specification document",
            "Sarah"
        )
        time.sleep(3)

        print("3. Decision notification")
        notifier.notify_decision(
            "Decided to use token bucket algorithm for rate limiting"
        )
        time.sleep(3)

        print("4. Key point notification")
        notifier.notify_key_point(
            "Q1 roadmap includes API project completion and security review"
        )
        time.sleep(3)

        print("5. Summary notification")
        notifier.notify_summary(
            "Meeting covered Q1 roadmap planning, API development status, "
            "and security review scheduling. 3 action items identified.",
            "45 minutes"
        )
        time.sleep(3)

        print("\n✓ All test notifications sent!")
        print("Check your notification center if you missed any.\n")

        # Wait a bit for last notification to show
        time.sleep(2)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\n✗ Error: {e}")
    finally:
        notifier.stop()
        print("Notifier stopped")


if __name__ == '__main__':
    test_notifier()
