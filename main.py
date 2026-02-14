from contextlib import asynccontextmanager

from fastapi import FastAPI

from db.connection import Base, engine
from routers import entities, items, lists, services, summary, transactions


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Kei API", version="0.2.0", lifespan=lifespan)

app.include_router(entities.router)
app.include_router(transactions.router)
app.include_router(items.router)
app.include_router(services.router)
app.include_router(lists.router)
app.include_router(summary.router)


@app.get("/health")
def health():
    return {"status": "ok"}
