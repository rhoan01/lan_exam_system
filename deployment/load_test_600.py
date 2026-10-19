"""Dependency-free 600-connection burst test for the production server.

This is a transport/server smoke test. A full exam rehearsal with realistic
questions and laboratory computers is still required before examination day.
"""

import argparse
import asyncio
import statistics
import time
from urllib.parse import urlsplit


async def request_once(host, port, path, timeout, start_gate):
    await start_gate.wait()
    started = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "User-Agent: lan-exam-capacity-check\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(request.encode('ascii'))
        await writer.drain()
        status_line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        await asyncio.wait_for(reader.read(), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        status = int(status_line.split()[1])
        return status, time.perf_counter() - started, None
    except Exception as exc:
        return 0, time.perf_counter() - started, str(exc)


async def run(url, clients, timeout):
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or not parsed.hostname:
        raise ValueError('Only a complete http:// URL is supported.')
    host = parsed.hostname
    port = parsed.port or 80
    path = parsed.path or '/'
    if parsed.query:
        path += '?' + parsed.query

    start_gate = asyncio.Event()
    tasks = [
        asyncio.create_task(request_once(host, port, path, timeout, start_gate))
        for _ in range(clients)
    ]
    started = time.perf_counter()
    start_gate.set()
    results = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - started

    successful = [(status, latency) for status, latency, error in results if 200 <= status < 400]
    failures = [(status, error) for status, latency, error in results if not 200 <= status < 400]
    latencies = sorted(latency for status, latency in successful)

    print(f'URL: {url}')
    print(f'Concurrent clients: {clients}')
    print(f'Successful responses: {len(successful)}/{clients}')
    print(f'Total elapsed: {elapsed:.2f}s')
    if latencies:
        p95_index = min(len(latencies) - 1, int(len(latencies) * 0.95))
        print(f'Median latency: {statistics.median(latencies):.2f}s')
        print(f'95th percentile: {latencies[p95_index]:.2f}s')
        print(f'Max latency: {max(latencies):.2f}s')
    if failures:
        print(f'Failure examples: {failures[:5]}')
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1/login/')
    parser.add_argument('--clients', type=int, default=600)
    parser.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.url, args.clients, args.timeout)))


if __name__ == '__main__':
    main()
