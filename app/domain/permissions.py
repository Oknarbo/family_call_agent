"""Family-only authorization rules."""

from uuid import UUID

from app.domain.exceptions import UnauthorizedError


def authorize_family_access(requester_user_id: UUID | None, target_user_id: UUID) -> None:
    """Allow registered callers to access family data; reject anonymous callers."""

    if requester_user_id is None:
        raise UnauthorizedError
    if not isinstance(target_user_id, UUID):
        raise UnauthorizedError
