"""Domain exceptions and their HTTP mapping.

Repositories raise these; the handlers in ``main`` turn them into responses.
A cross-workspace lookup raises ``NotFoundError`` exactly like a missing row does —
the API never confirms that a foreign entity exists.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class NotFoundError(Exception):
    def __init__(self, entity: str = "resource") -> None:
        super().__init__(f"{entity} not found")
        self.entity = entity


class ConflictError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ForbiddenError(Exception):
    def __init__(self, detail: str = "forbidden") -> None:
        super().__init__(detail)
        self.detail = detail


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": exc.detail})

    @app.exception_handler(ForbiddenError)
    async def _forbidden(_: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": exc.detail})
