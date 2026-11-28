import argparse
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SERVICES = ('auth', 'users', 'orders')
WEIGHTS = (0.35, 0.25, 0.40)
ROUTES = {
    'auth': (('POST', '/login'), ('POST', '/refresh')),
    'users': (('GET', '/profile'), ('PATCH', '/profile')),
    'orders': (('GET', '/orders'), ('POST', '/orders'), ('GET', '/orders/{id}')),
}
BASE_LATENCY = {'auth': 45, 'users': 70, 'orders': 120}
INCIDENT_FILE = Path('/tmp/incident')


def event(timestamp, incident=False):
    service = random.choices(SERVICES, weights=WEIGHTS)[0]
    method, endpoint = random.choice(ROUTES[service])
    affected = incident and service == 'orders'
    p5xx = 0.35 if affected else 0.01
    draw = random.random()
    if draw < p5xx:
        status = random.choice((500, 503))
    elif draw < p5xx + 0.04:
        status = random.choice((400, 401, 404))
    else:
        status = 201 if method == 'POST' and service == 'orders' else 200
    median = BASE_LATENCY[service] * (7 if affected else 1)
    duration = min(30000, max(1, round(random.lognormvariate(0, 0.45) * median)))
    return {
        'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'service': service,
        'endpoint': endpoint,
        'method': method,
        'status_code': status,
        'duration_ms': duration,
    }


def insert(events):
    url = os.environ.get('CH_URL', 'http://clickhouse:8123').rstrip('/')
    sql = 'INSERT INTO lab4.requests FORMAT JSONEachRow'
    payload = ('\n'.join(json.dumps(item) for item in events) + '\n').encode()
    request = Request(
        f'{url}/?{urlencode({"query": sql})}', data=payload,
        headers={
            'X-ClickHouse-User': os.environ.get('CH_USER', 'lab_writer'),
            'X-ClickHouse-Key': os.environ['CH_PASSWORD'],
            'Content-Type': 'application/x-ndjson',
        }, method='POST',
    )
    with urlopen(request, timeout=15) as response:
        response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backfill-minutes', type=int, default=0,
                        help='Insert normal historical events, then exit')
    args = parser.parse_args()
    size = int(os.environ.get('BATCH_SIZE', '500'))
    interval = int(os.environ.get('BATCH_INTERVAL', '5'))
    if size <= 0 or interval <= 0 or not 0 <= args.backfill_minutes <= 1440:
        parser.error('positive batch settings and 0..1440 backfill minutes required')
    if args.backfill_minutes:
        end = datetime.now(timezone.utc).replace(microsecond=0)
        start = end - timedelta(minutes=args.backfill_minutes)
        total = 0
        while start < end:
            # Same approximate events/second as the live generator.
            seconds = min(interval, int((end - start).total_seconds()))
            rows = max(1, round(size * seconds / interval))
            insert([event(start + timedelta(seconds=random.randrange(seconds)))
                    for _ in range(rows)])
            total += rows
            start += timedelta(seconds=seconds)
        print(f'Backfill inserted {total} events')
        return
    while True:
        started = time.monotonic()
        now = datetime.now(timezone.utc)
        incident = INCIDENT_FILE.exists()
        events = [event(now - timedelta(seconds=random.randrange(interval)), incident)
                  for _ in range(size)]
        try:
            insert(events)
            print(f'Inserted {len(events)} events; mode={"incident" if incident else "normal"}')
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            print(f'INSERT failed, batch discarded: {exc}', flush=True)
        time.sleep(max(0, interval - (time.monotonic() - started)))


if __name__ == '__main__':
    main()
