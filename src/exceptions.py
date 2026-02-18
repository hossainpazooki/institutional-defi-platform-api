"""Global exception hierarchy and HTTP exception factories.

Adopts the Console's exception pattern (base class + domain errors + HTTP factories)
and extends with Workbench error categories.

Domain-specific exceptions live in src/{domain}/exceptions.py and inherit from
AppException.
"""

from fastapi import HTTPException, status

# ── Base exception ───────────────────────────────────────────────────────


class AppException(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str = "An error occurred"):
        self.message = message
        super().__init__(self.message)


# ── Common domain exceptions ─────────────────────────────────────────────


class EntityNotFoundError(AppException):
    """Raised when a requested entity is not found."""

    def __init__(self, entity_type: str, entity_id: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} not found: {entity_id}")


class ValidationError(AppException):
    """Raised when input validation fails beyond Pydantic checks."""

    pass


class ServiceUnavailableError(AppException):
    """Raised when an external service or dependency is unavailable."""

    def __init__(self, service: str, reason: str = "Service unavailable"):
        self.service = service
        super().__init__(f"{service}: {reason}")


class AuthenticationError(AppException):
    """Raised when authentication fails."""

    pass


class AuthorizationError(AppException):
    """Raised when the user lacks permission for an action."""

    pass


# ── HTTP exception factories ────────────────────────────────────────────


def not_found(detail: str) -> HTTPException:
    """Create a 404 Not Found exception."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def bad_request(detail: str) -> HTTPException:
    """Create a 400 Bad Request exception."""
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def unauthorized(detail: str = "Not authenticated") -> HTTPException:
    """Create a 401 Unauthorized exception."""
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def forbidden(detail: str = "Not authorized") -> HTTPException:
    """Create a 403 Forbidden exception."""
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def internal_error(detail: str = "Internal server error") -> HTTPException:
    """Create a 500 Internal Server Error exception."""
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def service_unavailable(detail: str = "Service unavailable") -> HTTPException:
    """Create a 503 Service Unavailable exception."""
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
