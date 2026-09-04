import argparse
import asyncio
import httpx

from techpulse.event_factory import create_event
from techpulse.sender import send_event

async def run(target: str, rate: float):
    interval = 60 / rate
    async with httpx.AsyncClient() as client:
        while True:
            event = create_event()
            try:
                result = await send_event(client, target, event)
                print(result)
            except Exception as exc:
                print(f"send failed: {exc}")
            await asyncio.sleep(interval)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="http://127.0.0.1:8000/events")
    parser.add_argument("--rate", type=float, default=60)
    args = parser.parse_args()
    asyncio.run(run(args.target, args.rate))

if __name__ == "__main__":
    main()
