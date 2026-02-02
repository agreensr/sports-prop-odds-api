# Performance Tests

Load testing using **Locust** for the Sports-Bet-AI-API.

## What is Locust?

Locust is an open-source load testing tool that uses Python to define user behavior. Unlike traditional tools that simulate concurrent threads, Locust uses **event-driven coroutines** (via gevent), allowing it to simulate thousands of users from a single machine.

## Installation

```bash
# Already in requirements.txt
pip install locust
```

## Running Tests

### Web UI Mode (Recommended for Development)

```bash
# From project root
cd tests/performance

# Start with web UI at http://localhost:8089
locust

# Or specify host
locust --host http://localhost:8001
```

**Web UI Features:**
- Real-time charts (requests/sec, response times, failure rates)
- Start/Stop/Reset controls
- Adjust user count and spawn rate dynamically
- Download test results as CSV

### Headless Mode (CI/CD)

```bash
# Run 100 users, spawning 10 per second, for 60 seconds
locust --headless --users 100 --spawn-rate 10 --run-time 60s

# Quick smoke test (10 users, 10 seconds)
locust --headless --users 10 --spawn-rate 5 --run-time 10s -f locustfile.py QuickTestUser

# Stress test (ramp to 500 users)
locust --headless --users 500 --spawn-rate 50 --run-time 120s -f locustfile.py StressTestUser
```

### Remote Master/Worker (Distributed Testing)

```bash
# Master node (coordinates workers)
locust --master --expect-workers=4 --host http://api.example.com

# Worker nodes (execute the load)
locust --worker --master-host=localhost
```

## Test Scenarios

### User Types

| User Type | Description | Requests/sec | Pattern |
|-----------|-------------|--------------|---------|
| `NBAUser` | Browsing NBA predictions/players | ~0.5 | Realistic (1-3s wait) |
| `NFLUser` | Browsing NFL predictions | ~0.3 | Slower (2-4s wait) |
| `AccuracyUser` | Checking prediction accuracy | ~0.1 | Infrequent (5-10s wait) |
| `MetricsUser` | Prometheus metrics scraping | ~0.07 | Periodic (10-15s wait) |
| `MixedTrafficUser` | Realistic mixed traffic | ~0.4 | Weighted distribution |
| `QuickTestUser` | Quick smoke tests | ~1-2 | Minimal wait |
| `StressTestUser` | Aggressive stress testing | ~2-5 | Very aggressive |

### Running Specific Scenarios

```bash
# Test only NBA endpoints
locust -f locustfile.py NBAUser --users 50

# Test mixed traffic (70% NBA, 20% accuracy, 10% health)
locust -f locustfile.py MixedTrafficUser --users 100

# Stress test heavy endpoints
locust -f locustfile.py StressTestUser --users 200
```

## Interpreting Results

### Key Metrics

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| Failure Rate | < 1% | 1-5% | > 5% |
| Avg Response Time | < 200ms | 200-500ms | > 500ms |
| 95th Percentile | < 500ms | 500-1000ms | > 1000ms |
| 99th Percentile | < 1000ms | 1-2s | > 2s |

### Common Issues

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| High failure rate at low load | Configuration/bug | Fix application errors |
| Sudden spike in failures | Rate limiting | Increase rate limit or reduce load |
| Gradual slowdown | Memory leak | Profile and fix memory issues |
| DB timeout errors | Database bottleneck | Add connection pooling, optimize queries |
| CPU saturation at low users | Inefficient code | Profile and optimize hot paths |

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Performance Tests

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Start API server
        run: |
          python -m uvicorn app.main:app &
          sleep 10  # Wait for server to start

      - name: Run performance tests
        run: |
          cd tests/performance
          locust --headless --users 50 --spawn-rate 5 --run-time 30s \
            --host http://localhost:8001 \
            --csv results/$(date +%Y%m%d-%H%M%S)

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: locust-results
          path: tests/performance/results/
```

## Best Practices

1. **Start Small** - Begin with 10-20 users to establish baseline
2. **Ramp Gradually** - Increase by 2x increments to find breaking point
3. **Monitor Resources** - Watch CPU, memory, DB connections during tests
4. **Test Realistic Scenarios** - Use `MixedTrafficUser` for production-like load
5. **Run Regularly** - Add to CI/CD to catch performance regressions
6. **Document Baselines** - Track expected RPS and response times

## Troubleshooting

### "Connection refused" errors
- Ensure the API server is running on the expected port
- Check `--host` parameter matches your server address

### "Module not found" errors
- Run from project root: `cd tests/performance && locust`
- Or use `-f` flag: `locust -f tests/performance/locustfile.py`

### High memory usage during tests
- Locust memory grows with request history
- Use `--run-time` for fixed duration tests
- Results can be exported and Locust restarted

### Tests too fast/slow
- Adjust `wait_time` in user classes
- Change `--spawn-rate` for user ramp speed
