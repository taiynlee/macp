"""Quick test — inspect resume error and try different value formats."""
import asyncio
import httpx

BASE = "http://127.0.0.1:2024"
ASSISTANT = "fe096781-5601-53d2-b2f6-0d3403f7e9ca"


async def try_resume(c, tid, value):
    r = await c.post(f"/threads/{tid}/runs/wait", json={
        "assistant_id": ASSISTANT,
        "command": {"resume": value},
        "resumable": True,
    })
    data = r.json()
    print(f"  value={value!r} → keys={list(data.keys())[:6]}, error={data.get('__error__','')[:200]}")
    return data


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=120) as c:
        r = await c.post("/threads", json={})
        tid = r.json()["thread_id"]
        print(f"thread: {tid}")

        r = await c.post(f"/threads/{tid}/runs/wait", json={
            "assistant_id": ASSISTANT,
            "input": {"messages": [{"role": "user", "content": "list tables in tommy db"}]},
            "resumable": True,
        })
        data = r.json()
        interrupts = data.get("__interrupt__", [])
        print(f"interrupts: {len(interrupts)}")
        if interrupts:
            print(f"  interrupt id: {interrupts[0]['id']}")
            print(f"  allowed_decisions: {interrupts[0]['value'].get('review_configs',[{}])[0].get('allowed_decisions')}")

        # try different resume formats
        await try_resume(c, tid, "approve")
        await try_resume(c, tid, {"action": "approve"})
        await try_resume(c, tid, [{"action": "approve"}])


asyncio.run(main())
