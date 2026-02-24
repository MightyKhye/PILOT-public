"""Enhanced CLI to control Meeting Listener with query and document features."""
import sys
import time
from pathlib import Path
from tkinter import Tk, filedialog

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.meeting_manager import MeetingManager, MeetingState
from src.query_interface import QueryInterface
from src.config import Config

def main():
    print("=" * 70)
    print(" ASSISTANT")
    print("AI-Powered Meeting Intelligence")
    print("=" * 70)

    manager = MeetingManager()
    query_interface = QueryInterface(memory=manager.memory)

    # Show startup info
    num_meetings = len(manager.memory.memory_data['meetings'])
    num_docs = len(manager.memory.memory_data['documents'])
    print(f"\nLoaded: {num_meetings} previous meetings, {num_docs} documents")

    while True:
        print("\n" + "=" * 70)
        print("OPTIONS")
        print("=" * 70)
        print("  1. Start Recording")
        print("  2. Stop Recording")
        print("  3. View Status")
        print()
        print("  4. Ask Question (Query  knowledge)")
        print("  5. Upload  Document")
        print("  6. View Documents")
        print("  7. View Meeting History")
        print()
        print("  8. Learn  from Web (Build knowledge base)")
        print("  9. View Web Knowledge Status")
        print()
        print("  0. Exit")

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            print("\n" + "-" * 70)
            print("[Starting recording...]")
            print("-" * 70)
            print("The system will:")
            print("  - Capture ambient audio from your microphone")
            print("  - Transcribe every 30 seconds with AssemblyAI")
            print("  - Analyze with Claude for action items & decisions")
            print("  - Show Windows notifications")
            print("  - Remember everything for future reference")
            print()

            success = manager.start_meeting()
            if success:
                print("[OK] Recording started!")
            else:
                print("[ERROR] Failed to start recording")

        elif choice == "2":
            print("\n" + "-" * 70)
            print("[Stopping recording...]")
            print("-" * 70)
            summary_path = manager.stop_meeting()

            if summary_path:
                print(f"[OK] Recording stopped!")
                print(f"\nSummary saved to: {summary_path}")
                print(f"Also copied to: Downloads folder")
                print()
                info = manager.get_meeting_info()
                print(f"Meeting Duration: {info['duration']}")
                print(f"Chunks Processed: {info['chunks_processed']}")
                print(f"Analyses: {info['analyses']}")
            else:
                print("[ERROR] No recording in progress or failed to generate summary")

        elif choice == "3":
            print("\n" + "-" * 70)
            print("CURRENT STATUS")
            print("-" * 70)
            info = manager.get_meeting_info()
            print(f"State: {info['state']}")

            if info['state'] != 'idle':
                print(f"Meeting ID: {info['meeting_id']}")
                print(f"Duration: {info['duration']}")
                print(f"Chunks processed: {info['chunks_processed']}")
                print(f"Analyses: {info['analyses']}")
            else:
                print("No meeting in progress")

        elif choice == "4":
            print("\n" + "-" * 70)
            print("ASK A QUESTION")
            print("-" * 70)
            print("Ask anything about , past meetings, action items, decisions, etc.")
            print("Examples:")
            print("  - What training requirements were discussed?")
            print("  - What are the pending action items for Sarah?")
            print("  - What decisions were made about virtual training?")
            print()
            question = input("Your question: ").strip()

            if question:
                print("\n[Querying Claude with full meeting history...]")
                answer = query_interface.query(question)
                print("\n" + "-" * 70)
                print("ANSWER")
                print("-" * 70)
                print(answer)
                print("-" * 70)
            else:
                print("[ERROR] No question entered")

        elif choice == "5":
            print("\n" + "-" * 70)
            print("UPLOAD  DOCUMENTS")
            print("-" * 70)
            print("Drag & drop files here (select multiple in Explorer)")
            print("Tip: Ctrl+Click or Ctrl+A to select multiple, then drag all at once")
            print()
            doc_paths_str = input("Drop files here: ").strip()

            if doc_paths_str:
                    # Parse multiple file paths - Windows style
                    import re
                    file_paths = []

                    if '"' in doc_paths_str:
                        # Paths with quotes: "C:\path\file1.pdf" "C:\path\file2.pdf"
                        matches = re.findall(r'"([^"]+)"', doc_paths_str)
                        file_paths = matches if matches else [doc_paths_str.strip('"').strip("'")]
                    else:
                        # Paths without quotes: C:\path\file1.pdf C:\path\file2.pdf
                        # Split on whitespace that comes before a drive letter pattern
                        paths = re.split(r'\s+(?=[A-Z]:\\)', doc_paths_str)
                        file_paths = [p.strip() for p in paths if p.strip()]

                    total_files = len(file_paths)
                    print(f"\nFound {total_files} file(s) to upload")
                    print("-" * 70)

                    added_count = 0
                    skipped_count = 0
                    updated_count = 0
                    failed_files = []

                    for idx, file_path_str in enumerate(file_paths, 1):
                        doc_path = Path(file_path_str)
                        percentage = int((idx / total_files) * 100)

                        print(f"\n[{idx}/{total_files}] ({percentage}%) Processing: {doc_path.name}")

                        if doc_path.exists():
                            status = query_interface.add_rems_document(doc_path)
                            if status == 'added':
                                print(f"    ✓ Added successfully")
                                added_count += 1
                            elif status == 'duplicate':
                                print(f"    ⊘ Skipped - Already uploaded")
                                skipped_count += 1
                            elif status == 'updated':
                                print(f"    ↻ Updated existing document")
                                updated_count += 1
                            else:  # error
                                print(f"    ✗ Failed to add")
                                failed_files.append(doc_path.name)
                        else:
                            print(f"    ✗ File not found")
                            failed_files.append(doc_path.name)

                    # Summary
                    print("\n" + "=" * 70)
                    print(f"UPLOAD COMPLETE")
                    print(f"  Added: {added_count}")
                    print(f"  Skipped (duplicates): {skipped_count}")
                    if updated_count > 0:
                        print(f"  Updated: {updated_count}")
                    if failed_files:
                        print(f"  Failed: {len(failed_files)}")
                        print(f"\nFailed files:")
                        for fname in failed_files:
                            print(f"  - {fname}")
                    print("=" * 70)
            else:
                print("[Cancelled] No files dropped")

        elif choice == "6":
            print("\n" + "-" * 70)
            print("UPLOADED DOCUMENTS")
            print("-" * 70)
            docs = query_interface.list_documents()
            if docs:
                for i, doc in enumerate(docs, 1):
                    print(f"  {i}. {doc}")
            else:
                print("No documents uploaded yet")

        elif choice == "7":
            print("\n" + "-" * 70)
            print("MEETING HISTORY")
            print("-" * 70)
            summary = query_interface.get_meeting_summary()
            print(summary)

        elif choice == "8":
            print("\n" + "-" * 70)
            print("LEARN  FROM WEB")
            print("-" * 70)
            print("This will research and compile comprehensive public knowledge about:")
            print("  •  product information")
            print("  •  program requirements and safety")
            print("  • Training and certification procedures")
            print("  • Clinical guidelines and protocols")
            print("  • Provider requirements and compliance")
            print("  • FDA regulations and documentation")
            print()
            print("This may take 30-60 seconds...")
            print()

            confirm = input("Continue? (y/n): ").strip().lower()
            if confirm == 'y':
                print("\n[Learning from public sources...]")
                results = query_interface.learn_product_from_web()

                if results['success']:
                    print("\n[OK] Learning complete!")
                    print(f"  Sources researched: {results['sources_found']}")
                    print(f"  Topics learned: {results['topics_learned']}")
                    print("\nKnowledge base updated and ready for queries.")
                    print("Saved to: meetings/_Knowledge_Base.md")
                else:
                    print(f"\n[ERROR] Learning failed: {results['summary']}")
            else:
                print("Cancelled")

        elif choice == "9":
            print("\n" + "-" * 70)
            print("WEB KNOWLEDGE STATUS")
            print("-" * 70)
            status = query_interface.get_web_knowledge_status()
            print(status)

        elif choice == "0":
            print("\nExiting...")
            if manager.get_state() != MeetingState.IDLE:
                print("Stopping current recording first...")
                manager.stop_meeting()
            manager.cleanup()
            break

        else:
            print("[ERROR] Invalid choice")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
