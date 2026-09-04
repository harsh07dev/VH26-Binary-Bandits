import httpx

async def send_event(client: httpx.AsyncClient, target: str, event: dict):
    response = await client.post(target, json=event, timeout=5.0)
    response.raise_for_status()
    return response.json()
