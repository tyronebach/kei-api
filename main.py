from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from config import settings
from db.connection import SessionLocal
from routers import entities, items, lists, services, summary, transactions

app = FastAPI(title="Kei API", version="0.2.0")

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

app.include_router(entities.router)
app.include_router(transactions.router)
app.include_router(items.router)
app.include_router(services.router)
app.include_router(lists.router)
app.include_router(summary.router)


@app.on_event("startup")
def startup_safety_checks():
    if (
        settings.api_token == "changeme"
        and not settings.allow_insecure_default_token
    ):
        raise RuntimeError(
            "KEI_API_TOKEN is using the insecure default 'changeme'. "
            "Set a strong KEI_API_TOKEN or set KEI_ALLOW_INSECURE_DEFAULT_TOKEN=true for local-only testing."
        )


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
