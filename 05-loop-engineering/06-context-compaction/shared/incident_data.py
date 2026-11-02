"""
Simulated log data for the compaction demos.

The logs are deliberately long, so a loop that reads a few services quickly outgrows a small
context budget. A handful of important facts are buried in each one, which tells you whether
they survive compaction.
"""

import random

MAX_NOISE_LINES = 120

SERVICES = [
    "api-gateway",
    "auth",
    "billing",
    "catalog",
    "notifications",
    "orders",
    "payments",
    "search",
]

# Facts the final report must retain, including ones found long before any compaction
SIGNALS = {
    "api-gateway": "ERROR upstream 'payments' returned 503 for 18% of requests from 14:07 UTC",
    "auth": "INFO token cache hit rate normal at 99.2%; no errors during the incident window",
    "billing": "WARN invoice job INV-7731 retried 3 times, waiting on the payments service",
    "catalog": "INFO no errors; deploy catalog-v88 finished at 11:02 UTC, well before the incident",
    "notifications": "WARN queue depth reached 41,200 at 14:19 UTC after payment events stalled",
    "orders": "ERROR 2,318 orders stuck in PENDING_PAYMENT between 14:07 and 14:31 UTC",
    "payments": "FATAL connection pool exhausted (max=20) after deploy payments-v412 at 14:06 UTC; "
    "config changed db_pool_size from 200 to 20",
    "search": "INFO no errors; index rebuild ran at 03:00 UTC as scheduled",
}


def read_service_logs(service: str) -> str:
    """Return a long, reproducible log for one service, with its signal line buried inside."""
    if service not in SERVICES:
        raise ValueError(f"Unknown service {service!r}. Known services: {', '.join(SERVICES)}")

    rng = random.Random(service)
    lines = [
        f"14:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d} DEBUG "
        f"{service} request_id={rng.getrandbits(48):012x} latency_ms={rng.randint(3, 240)} "
        f"status=200 path=/internal/v1/health"
        for _ in range(MAX_NOISE_LINES)
    ]
    lines.insert(rng.randint(40, 80), f"14:20:00 {SIGNALS[service]}")
    return "\n".join(lines)
