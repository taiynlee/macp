"""
Example agent — extend AgentWrapper and implement handle_task.
Run: python example_agent.py
"""

import asyncio
import logging

from wrapper import AgentWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

SERVER = "ws://localhost:8000/ws/agent"


class ExampleAgent(AgentWrapper):
    name = "example_agent"
    capabilities = ["echo", "ping"]

    async def handle_task(self, msg: dict) -> str:
        content = msg.get("content", "")

        if content.strip().lower() == "ping":
            return "pong"

        # default: echo back
        return f"echo: {content}"

    async def on_connect(self) -> None:
        # send alert on startup so operator knows we're alive
        await self.send_alert(f"{self.name} online and ready", priority="normal")

    async def on_message(self, msg: dict) -> None:
        print(f"[{self.name}] received {msg.get('type')}: {msg.get('content', '')}")


if __name__ == "__main__":
    ExampleAgent(server_url=SERVER).run()
