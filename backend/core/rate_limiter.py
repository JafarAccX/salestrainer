"""
Simple in-memory rate limiter for FastAPI.
No external dependencies — uses a sliding window per IP.
"""
import time
from collections import defaultdict
from fastapi import Request, HTTPException


class RateLimiter:
    """Per-IP sliding-window rate limiter."""

    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window

        # Prune expired entries
        hits = self._requests[ip]
        self._requests[ip] = [t for t in hits if t > window_start]

        if len(self._requests[ip]) >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {self.max_requests} requests per {self.window}s.",
            )
        self._requests[ip].append(now)


# Pre-configured limiters for different tiers
chat_limiter = RateLimiter(max_requests=30, window_seconds=60)     # 30 chat messages/min
mock_call_limiter = RateLimiter(max_requests=5, window_seconds=60) # 5 call starts/min
eval_limiter = RateLimiter(max_requests=10, window_seconds=60)     # 10 evaluations/min
