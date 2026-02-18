from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from db.connection import SessionLocal
from routers import entities, items, lists, services, summary, transactions

app = FastAPI(title="Kei API", version="0.2.0")

app.include_router(entities.router)
app.include_router(transactions.router)
app.include_router(items.router)
app.include_router(services.router)
app.include_router(lists.router)
app.include_router(summary.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status": exc.status_code,
            "message": exc.detail,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": True,
            "status": 422,
            "message": "Validation error",
            "details": exc.errors(),
        },
    )


@app.get("/health")
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
    finally:
        db.close()
