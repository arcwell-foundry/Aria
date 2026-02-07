# Rate Limiter

## Overview
The rate limiter protects API endpoints from abuse using in-memory sliding window tracking. It implements a token bucket algorithm with configurable limits per endpoint.

## Configuration
Rate limits are configured per endpoint in the API route decorators:

```python
from src.core.rate_limiter import rate_limit

@router.get("/api/endpoint")
@rate_limit(requests=100, window_seconds=60)  # 100 requests per minute
async def endpoint():
    ...
```

### Default Limits
- **Authentication endpoints**: 5 requests per minute
- **API routes**: 100 requests per minute
- **WebSocket connections**: 10 connections per minute
- **Data export**: 1 request per 5 minutes

## Usage

### Basic Rate Limiting
```python
from fastapi import APIRouter, HTTPException
from src.core.rate_limiter import rate_limit, RateLimitExceeded

router = APIRouter()

@router.post("/api/data")
@rate_limit(requests=50, window_seconds=60)
async def create_data():
    return {"message": "Success"}
```

### Handling Rate Limit Errors
```python
from src.core.rate_limiter import RateLimitExceeded

@router.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "retry_after": exc.retry_after
        },
        headers={"Retry-After": str(exc.retry_after)}
    )
```

### Custom Rate Limits by User Tier
```python
@router.get("/api/search")
@rate_limit(
    requests=lambda user: 1000 if user.tier == "premium" else 100,
    window_seconds=60
)
async def search(current_user: User = Depends(get_current_user)):
    ...
```

## Response Headers
Rate-limited responses include:

- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Requests remaining in window
- `X-RateLimit-Reset`: Unix timestamp when window resets
- `Retry-After`: Seconds until retry is allowed

## Production Considerations

### Scalability
The current implementation uses in-memory storage. For production deployment:

1. **Multi-instance deployments**: Use Redis for distributed rate limiting
2. **Persistence**: Rate limit state is lost on restart (acceptable for most use cases)
3. **Memory usage**: Each tracked endpoint uses ~1KB per client

### Configuration
```python
# In src/core/config.py
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true")
RATE_LIMIT_STORAGE = os.getenv("RATE_LIMIT_STORAGE", "memory")  # or "redis"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
```

### Monitoring
Rate limit violations are logged with structured data:
```json
{
  "event": "rate_limit_exceeded",
  "client_id": "user_123",
  "endpoint": "/api/search",
  "limit": 100,
  "window_seconds": 60
}
```

### Testing
```python
import pytest
from httpx import AsyncClient

async def test_rate_limiting(client: AsyncClient):
    responses = []
    for _ in range(105):  # Exceed limit of 100
        responses.append(await client.get("/api/search"))

    # First 100 should succeed
    assert sum(r.status_code == 200 for r in responses[:100]) == 100

    # Remaining should be rate limited
    assert all(r.status_code == 429 for r in responses[100:])
```

## Security Considerations

1. **Client identification**: Use user IDs for authenticated routes, IP addresses for public endpoints
2. **Distributed attacks**: Implement IP-based blocking for coordinated abuse
3. **Burst protection**: The sliding window prevents request clustering
4. **Graduated limits**: Consider implementing exponential backoff for repeat offenders

## Migration to Redis
For distributed deployments, replace the in-memory store:

```python
import aioredis

class RedisRateLimiter:
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url)

    async def check_limit(self, key: str, limit: int, window: int) -> bool:
        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, window)
        return current <= limit
```
