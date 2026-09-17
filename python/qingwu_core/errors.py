class QingwuError(Exception):
    """Base error that can safely cross the JSON-RPC boundary."""

    code = "qingwu_error"

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": str(self)}


class ValidationError(QingwuError):
    code = "validation_error"


class NotFoundError(QingwuError):
    code = "not_found"


class ConflictError(QingwuError):
    code = "conflict"


class AIUnavailableError(QingwuError):
    code = "ai_unavailable"
