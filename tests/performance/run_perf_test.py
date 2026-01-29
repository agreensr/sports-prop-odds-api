#!/usr/bin/env python3
"""
Convenience script for running performance tests.

Usage:
    python tests/performance/run_perf_test.py --help
    python tests/performance/run_perf_test.py quick
    python tests/performance/run_perf_test.py --users 100 --duration 60
"""
import argparse
import subprocess
import sys
import os


def run_locust(args):
    """Run locust with the specified arguments."""
    # Change to the performance tests directory
    perf_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(perf_dir)

    # Build locust command
    cmd = ["locust", "-f", "locustfile.py"]

    # Add user class if specified
    if args.user_class:
        cmd.extend([args.user_class])

    # Add host
    host = args.host or "http://localhost:8001"
    cmd.extend(["--host", host])

    # Add headless mode unless web requested
    if not args.web:
        cmd.append("--headless")

    # Add user count
    if args.users:
        cmd.extend(["--users", str(args.users)])

    # Add spawn rate
    if args.spawn_rate:
        cmd.extend(["--spawn-rate", str(args.spawn_rate)])

    # Add run time (for headless mode)
    if args.run_time:
        cmd.extend(["--run-time", args.run_time])

    # Add CSV output
    if args.csv:
        csv_prefix = args.csv or "results/perf_test"
        cmd.extend(["--csv", csv_prefix])

    # Print command and run
    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd)

    sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(
        description="Run performance tests with Locust",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick smoke test (10 users, 10 seconds)
  python run_perf_test.py quick

  # Web UI mode (interactive)
  python run_perf_test.py --web

  # Standard load test (100 users, 60 seconds)
  python run_perf_test.py --users 100 --duration 60s

  # Stress test (500 users)
  python run_perf_test.py stress --users 500

  # Test specific user class
  python run_perf_test.py --user-class NBAUser --users 50

  # Save results to CSV
  python run_perf_test.py --csv results/my_test --users 100 --duration 60s
        """
    )

    parser.add_argument("--web", action="store_true",
                        help="Run with web UI (default: headless mode)")
    parser.add_argument("--host", type=str,
                        help="API host URL (default: http://localhost:8001)")
    parser.add_argument("--users", "-u", type=int,
                        help="Number of users to simulate")
    parser.add_argument("--spawn-rate", "-r", type=int,
                        help="Users spawned per second")
    parser.add_argument("--duration", "-d", type=str,
                        help="Test duration (e.g., 30s, 5m, 1h)")
    parser.add_argument("--csv", type=str,
                        help="Save results to CSV with prefix")
    parser.add_argument("--user-class", type=str,
                        choices=["NBAUser", "NFLUser", "AccuracyUser",
                                "MetricsUser", "MixedTrafficUser",
                                "QuickTestUser", "StressTestUser"],
                        help="Specific user class to test")

    # Convenience shortcuts
    parser.add_argument("quick", nargs="?",
                        help="Quick smoke test (shorthand for --users 10 --duration 10s)")
    parser.add_argument("stress", nargs="?",
                        help="Stress test (shorthand for --user-class StressTestUser)")

    args = parser.parse_args()

    # Handle quick shorthand
    if args.quick == "quick" or (args.quick is None and not any([
        args.users, args.web, args.stress
    ])):
        args.users = 10
        args.run_time = "10s"
        args.user_class = "QuickTestUser"

    # Handle stress shorthand
    if args.stress == "stress":
        args.user_class = "StressTestUser"
        if not args.users:
            args.users = 200

    # Map duration to run_time
    if args.duration:
        args.run_time = args.duration

    # Set spawn rate default based on users
    if args.users and not args.spawn_rate:
        args.spawn_rate = max(1, args.users // 10)  # 10 seconds to ramp up

    run_locust(args)


if __name__ == "__main__":
    main()
