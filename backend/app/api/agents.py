from fastapi import APIRouter

from ..core.registry import registry

router = APIRouter(tags=["agents"])


@router.get("/agents")
async def list_agents() -> list[dict]:
    return registry.list_agents()
