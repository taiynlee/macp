from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.agents import router as agents_router
from .api.ws import router as ws_router
from .core.config import settings

app = FastAPI(title="MACP — Multi-Agents Communication Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(agents_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
