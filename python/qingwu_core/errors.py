class QingwuError(Exception):
    """Base error that can safely cross the JSON-RPC boundary."""

    code = "qingwu_error"

    def __init__(self, message: str, *, reason: str | None = None):
        super().__init__(message)
        self.reason = reason

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"code": self.code, "message": str(self)}
        if self.reason:
            payload["reason"] = self.reason
        return payload


class ValidationError(QingwuError):
    code = "validation_error"


class NotFoundError(QingwuError):
    code = "not_found"


class ConflictError(QingwuError):
    code = "conflict"


class AIUnavailableError(QingwuError):
    code = "ai_unavailable"
