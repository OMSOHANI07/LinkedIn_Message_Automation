"""CLI: bulk-import Meera's backlog of .txt/.md notes.

Usage:
    python -m app.cli import-notes [--folder notes]
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app.config import settings
from app.db.session import init_db, session_scope
from app.pipeline.orchestrator import import_notes_from_folder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def import_notes(folder: Path) -> None:
    init_db()
    with session_scope() as session:
        imported = import_notes_from_folder(session, folder)
        previews = [(note.id, note.text[:60] + ("..." if len(note.text) > 60 else "")) for note in imported]
    logger.info("Imported %d new note(s) from %s", len(previews), folder)
    for note_id, preview in previews:
        print(f"  [{note_id}] {preview}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Skinstinct assistant CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import-notes", help="Bulk import a folder of .txt/.md notes")
    import_parser.add_argument(
        "--folder", type=Path, default=settings.notes_import_dir, help="Folder to import from (default: notes/)"
    )

    args = parser.parse_args()
    if args.command == "import-notes":
        import_notes(args.folder)


if __name__ == "__main__":
    main()
