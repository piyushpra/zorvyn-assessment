from typing import Any, Dict, Optional

from pydantic import ValidationError


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details is not None:
            payload["error"]["details"] = self.details
        return payload


def from_validation_error(error: ValidationError) -> AppError:
    details = []
    for item in error.errors(include_url=False):
        details.append(
            {
                "field": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
        )
    return AppError(
        status_code=422,
        code="validation_error",
        message="Request validation failed.",
        details=details,
    )
