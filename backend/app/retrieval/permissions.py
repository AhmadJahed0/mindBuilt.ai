"""Permission resolution — runs BEFORE every vector search, never after.

This is the core security boundary from the architecture doc: the agent
never gets to pick which documents it searches. SQL decides that first,
based on the authenticated user, and vector search is filtered to the
result. Nothing here should ever accept a caller-supplied document scope
without checking it against this resolution.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentPermission, User
from app.retrieval.vector_store import COMPANY_SHARED_COLLECTION, personal_workspace_id


def resolve_accessible_document_ids(db: Session, user_id: int) -> list[int]:
    """Returns every document_id this user may read: every company-wide
    shared document, documents they privately own, documents privately
    owned by their department, plus documents explicitly shared with them
    via document_permissions. The "shared" visibility check is what makes
    this consistent with the (deliberately unfiltered) /documents library
    listing — before it, a document everyone could see in the library
    could still be invisible to chat retrieval for anyone but its owner."""
    user = db.get(User, user_id)

    company_wide = db.execute(
        select(Document.id).where(Document.visibility == "shared")
    ).scalars().all()

    owned = db.execute(
        select(Document.id).where(Document.owner_user_id == user_id)
    ).scalars().all()

    department_owned = []
    if user and user.department_id:
        department_owned = db.execute(
            select(Document.id).where(Document.owner_department_id == user.department_id)
        ).scalars().all()

    explicitly_shared = db.execute(
        select(DocumentPermission.document_id).where(DocumentPermission.user_id == user_id)
    ).scalars().all()

    return list(set(company_wide) | set(owned) | set(department_owned) | set(explicitly_shared))


def resolve_workspace_ids_for_user(user_id: int) -> list[str]:
    """Which Chroma collections to query for this user: their own private
    workspace plus the company-wide shared one. Team/project workspaces
    (architecture doc Section 3's full hierarchy) aren't built yet — they
    need DKK's real org structure to mean anything."""
    return [personal_workspace_id(user_id), COMPANY_SHARED_COLLECTION]
