from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import WebSocket


@dataclass
class AgentInfo:
    name: str
    capabilities: list[str]
    ws: WebSocket
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schedule: list[dict] = field(default_factory=list)


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}

    def register(self, info: AgentInfo) -> None:
        self._agents[info.name] = info

    def unregister(self, name: str) -> None:
        self._agents.pop(name, None)

    def heartbeat(self, name: str) -> None:
        if agent := self._agents.get(name):
            agent.last_heartbeat = datetime.now(timezone.utc)

    def set_schedule(self, name: str, jobs: list[dict]) -> None:
        if agent := self._agents.get(name):
            agent.schedule = jobs

    def report_job(self, name: str, job_name: str, success: bool) -> None:
        if agent := self._agents.get(name):
            for job in agent.schedule:
                if job.get("name") == job_name:
                    job["last_success"] = success
                    break

    def get(self, name: str) -> AgentInfo | None:
        return self._agents.get(name)

    def list_agents(self) -> list[dict]:
        return [
            {
                "name": a.name,
                "capabilities": a.capabilities,
                "connected_at": a.connected_at.isoformat(),
                "last_heartbeat": a.last_heartbeat.isoformat(),
                "schedule": a.schedule,
            }
            for a in self._agents.values()
        ]


registry = AgentRegistry()
