class DomainError(Exception):
    """Base domain error."""


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist."""


class ConflictError(DomainError):
    """Raised when an operation would violate a business invariant."""


class ValidationError(DomainError):
    """Raised when provided payload is structurally invalid."""
