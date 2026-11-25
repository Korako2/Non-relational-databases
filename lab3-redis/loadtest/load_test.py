"""HTTP load generator. Reports actual HTTP results, no synthetic numbers."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time
from uuid import uuid4

import httpx


def percentile_ms(samples, percentile):
    values = sorted(samples)
    if not values:
        return None
    index = max(0, min(len(values) - 1, int((len(values) - 1) * percentile / 100)))
    return round(values[index] * 1000, 2)


async def run(args):
    prefix = uuid4().hex[:12]  # Each run starts with a new logical client/window.
    sem = asyncio.Semaphore(args.concurrency)
    outcomes = []
    start = time.perf_counter()
    timeout = httpx.Timeout(15.0)
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)

    async with httpx.AsyncClient(timeout=timeout, limits=limits, trust_env=False) as client:
        async def send(index):
            client_id = f'load-{prefix}-{index % args.clients}'
            async with sem:
                t0 = time.perf_counter()
                try:
                    response = await client.get(
                        f'{args.url.rstrip("/")}/api/items',
                        headers={'X-Client-ID': client_id},
                    )
                    outcome = {'status': str(response.status_code), 'latency': time.perf_counter() - t0}
                except httpx.HTTPError as exc:
                    outcome = {'status': 'ERROR', 'latency': time.perf_counter() - t0, 'error': str(exc)}
                outcomes.append(outcome)

        await asyncio.gather(*(send(index) for index in range(args.requests)))

    elapsed = time.perf_counter() - start
    statuses = dict(sorted(Counter(r['status'] for r in outcomes).items()))
    latencies = [r['latency'] for r in outcomes]
    result = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'config': {'url': args.url, 'requests': args.requests, 'clients': args.clients,
                   'concurrency': args.concurrency},
        'elapsed_seconds': round(elapsed, 3),
        'throughput_requests_per_second': round(args.requests / elapsed, 2),
        'statuses': statuses,
        'latency_ms': {
            'mean': round(statistics.mean(latencies) * 1000, 2),
            'p50': percentile_ms(latencies, 50),
            'p95': percentile_ms(latencies, 95),
            'p99': percentile_ms(latencies, 99),
        },
        'errors': [r['error'] for r in outcomes if 'error' in r][:5],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Wrote results to {output}')
    return 1 if statuses.get('ERROR') or any(k not in ('200', '429') for k in statuses) else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Measure rate limiter API under load')
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--requests', type=int, default=200)
    parser.add_argument('--clients', type=int, default=1, help='Number of distinct X-Client-ID values')
    parser.add_argument('--concurrency', type=int, default=40)
    parser.add_argument('--out', help='Path for raw JSON result')
    options = parser.parse_args()
    if options.requests <= 0 or options.clients <= 0 or options.concurrency <= 0:
        parser.error('requests, clients and concurrency must be positive')
    raise SystemExit(asyncio.run(run(options)))
