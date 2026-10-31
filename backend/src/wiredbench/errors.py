"""The one error shape every API route returns."""

from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found.")
