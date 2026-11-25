from fastapi import Request
from fastapi.responses import JSONResponse

class DomainError(Exception):
    def __init__(self, message: str, code: str = "domain_error", status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)

async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})
