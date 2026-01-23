#!/usr/bin/env python3
"""
Lineup data fetch script for scheduled execution.

Fetches lineup projections from multiple sources (Rotowire, ESPN, NBA.com),
then stores in the database for minutes-based predictions.

Usage:
    python scripts/lineup_fetch.py

Cron scheduling (every 4 hours):
    0 */4 * * * cd /opt/sports-bet-ai-api && /opt/sports-bet-ai-api/venv/bin/python scripts/lineup_fetch.py >> /tmp/lineup_fetch_cron.log 2>&1
"""
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.nba.lineup_service import LineupService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/lineup_fetch_cron.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# Lineup sources to fetch from
LINEUP_SOURCES = ["rotowire", "espn", "nba"]


async def fetch_lineups(source: str = "rotowire"):
    """
    Fetch lineup data from a specific source.

    Args:
        source: Data source name (rotowire, espn, nba)

    Returns:
        dict with fetch results
    """
    db = SessionLocal()
    lineup_service = LineupService(db)

    try:
        logger.info(f"Fetching lineups from {source}...")

        # Fetch lineups
        lineups = await lineup_service.fetch_lineups_from_firecrawl(source)
        logger.info(f"Fetched {len(lineups)} lineup entries from {source}")

        # Ingest to database
        ingested = lineup_service.ingest_lineups(lineups)
        logger.info(f"Successfully ingested {ingested} new lineup entries to database")

        return {
            "source": source,
            "fetched": len(lineups),
            "ingested": ingested,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"Error fetching lineups from {source}: {e}", exc_info=True)
        return {
            "source": source,
            "status": "error",
            "error": str(e)
        }
    finally:
        db.close()


async def fetch_all_lineups():
    """
    Main function to fetch lineup data from all sources.

    Fetches from:
    1. Rotowire (primary source)
    2. ESPN (secondary)
    3. NBA.com (official depth charts)

    Returns:
        dict with results from each source
    """
    logger.info("=" * 60)
    logger.info("Lineup Fetch Script Started")
    logger.info("=" * 60)

    start_time = datetime.now()
    results = {
        "timestamp": start_time.isoformat(),
        "sources": {}
    }

    # Fetch from each source
    for source in LINEUP_SOURCES:
        logger.info(f"Processing source: {source}")
        result = await fetch_lineups(source)
        results["sources"][source] = result

        # Small delay between sources to avoid rate limiting
        await asyncio.sleep(2)

    # Calculate totals
    total_fetched = sum(r.get("fetched", 0) for r in results["sources"].values())
    total_ingested = sum(r.get("ingested", 0) for r in results["sources"].values())

    results["total_fetched"] = total_fetched
    results["total_ingested"] = total_ingested
    results["overall_status"] = "success" if total_ingested > 0 else "no_new_data"

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    results["duration_seconds"] = duration

    # Log summary
    logger.info("=" * 60)
    logger.info("Lineup Fetch Summary")
    logger.info("=" * 60)
    logger.info(f"Total fetched: {total_fetched}")
    logger.info(f"Total ingested: {total_ingested}")
    logger.info(f"Duration: {duration:.2f} seconds")
    logger.info(f"Status: {results['overall_status']}")
    logger.info("=" * 60)

    return results


def main():
    """Entry point for the script."""
    # Check if source argument provided
    import argparse
    parser = argparse.ArgumentParser(description="Fetch NBA lineup projections")
    parser.add_argument(
        "--source",
        choices=LINEUP_SOURCES,
        default=None,
        help="Specific source to fetch (default: all sources)"
    )
    args = parser.parse_args()

    if args.source:
        # Fetch from single source
        logger.info(f"Fetching lineups from single source: {args.source}")
        result = asyncio.run(fetch_lineups(args.source))
    else:
        # Fetch from all sources
        result = asyncio.run(fetch_all_lineups())

    # Exit with appropriate code
    if result.get("overall_status") == "success" or result.get("status") == "success":
        logger.info("Script completed successfully")
        sys.exit(0)
    else:
        logger.error("Script completed with errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
