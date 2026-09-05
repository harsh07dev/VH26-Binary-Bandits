# Local Redis Setup for PulseFlow

PulseFlow can optionally use Redis as the primary message queue backend, which provides better scalability for multi-process environments compared to the default `asyncio` backend.

## Starting Redis

To start the minimal local Redis environment:

```bash
docker compose up -d redis
```

This will run a Redis instance on standard port `6379` in the background, utilizing a named Docker volume (`redis_data`) so that events persist across container restarts.

## Stopping Redis

To stop the Redis container:

```bash
docker compose down
```

## Configuring PulseFlow to use Redis

By default, PulseFlow continues to use its in-memory `asyncio` queue backend. To switch to the Redis backend, you must explicitly set the backend via environment variables:

```bash
# Set the queue backend to Redis
export PULSEFLOW_QUEUE_BACKEND=redis

# (Optional) Override the Redis URL if using a custom port/host
export REDIS_URL=redis://localhost:6379
```

When `PULSEFLOW_QUEUE_BACKEND` is set to `redis`, the pipeline's QueueManager will automatically instantiate `RedisLaneQueue` for the CRITICAL, NORMAL, and BEST-EFFORT lanes instead of the default asyncio queues.
