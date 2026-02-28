#!/usr/bin/env python3
"""Quick batch tester for scrapers. Usage: python _test_batch.py key1 key2 ..."""
import sys, time, traceback
sys.path.insert(0, '.')

from scrapers.registry import SCRAPER_MAP

keys = sys.argv[1:]
if not keys:
    print("Usage: python _test_batch.py <scraper_key1> <scraper_key2> ...")
    sys.exit(1)

results = []
for key in keys:
    cls = SCRAPER_MAP.get(key)
    if not cls:
        print(f"\n{'='*60}\n[SKIP] '{key}' not found in registry\n{'='*60}")
        results.append((key, 'SKIP', 0, 0, 'Not in registry'))
        continue

    print(f"\n{'='*60}\n[TEST] {key} ({cls.__name__})\n{'='*60}")
    t0 = time.time()
    try:
        scraper = cls()
        jobs = scraper.scrape(max_pages=2)
        elapsed = time.time() - t0
        n = len(jobs)
        print(f"\n[RESULT] {key}: {n} jobs in {elapsed:.1f}s")
        if jobs:
            for j in jobs[:3]:
                title = j.get('title','?')[:80]
                loc = j.get('location','?')[:40]
                print(f"  - {title} | {loc}")
            if n > 3:
                print(f"  ... and {n-3} more")
        status = 'PASS' if n > 0 else 'FAIL(0)'
        results.append((key, status, n, elapsed, ''))
    except Exception as e:
        elapsed = time.time() - t0
        err = str(e)[:100]
        print(f"\n[ERROR] {key}: {err} ({elapsed:.1f}s)")
        traceback.print_exc()
        results.append((key, 'ERROR', 0, elapsed, err))

print(f"\n\n{'='*60}\nSUMMARY\n{'='*60}")
for key, status, n, t, note in results:
    print(f"  {status:10s} | {key:25s} | {n:4d} jobs | {t:6.1f}s | {note}")
