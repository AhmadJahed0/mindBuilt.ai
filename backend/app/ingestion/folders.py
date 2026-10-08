from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Folder


def get_or_create_folder_path(db: Session, path_parts: list[str]) -> int | None:
    """Ensures a folder hierarchy exists for path_parts (e.g. ['ProjectA',
    'Drawings']) and returns the leaf folder's id. Used when a browser
    folder-upload hands back each file's relative path — this is what
    preserves DKK's real directory structure instead of dumping every
    file into one flat pile."""
    if not path_parts:
        return None

    parent_id = None
    folder_id = None
    current_path = ""

    for part in path_parts:
        current_path = f"{current_path}/{part}" if current_path else part
        existing = db.execute(select(Folder).where(Folder.path == current_path)).scalar_one_or_none()
        if existing:
            folder_id = existing.id
            parent_id = existing.id
            continue

        folder = Folder(parent_folder_id=parent_id, name=part, path=current_path)
        db.add(folder)
        db.commit()
        db.refresh(folder)
        folder_id = folder.id
        parent_id = folder.id

    return folder_id
