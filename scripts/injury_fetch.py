#!/usr/bin/env python3
"""
Injury data fetch script for scheduled execution.

Fetches injury data from ESPN and NBA official reports,
then stores in the database for injury-aware predictions.

Usage:
    python scripts/injury_fetch.py

Cron scheduling (every 2 hours):
    0 */2 * * * cd /opt/sports-bet-ai-api && /opt/sports-bet-ai-api/venv/bin/python scripts/injury_fetch.py >> /tmp/injury_fetch_cron.log 2>&1
"""
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.nba.injury_service import InjuryService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/injury_fetch_cron.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def fetch_injuries():
    """
    Main function to fetch injury data from all sources.

    Fetches from:
    1. ESPN NBA News API
    2. NBA Official Injury Report (via Firecrawl)

    Returns:
        dict with counts from each source
    """
    db = SessionLocal()
    injury_service = InjuryService(db)

    try:
        logger.info("Starting injury fetch...")

        # Fetch from ESPN
        logger.info("Fetching injuries from ESPN...")
        espn_articles = await injury_service.fetch_espn_injury_news(limit=50)
        logger.info(f"Fetched {len(espn_articles)} injury articles from ESPN")

        # Parse ESPN articles for injury data
        espn_injuries = []
        for article in espn_articles:
            injury_data = parse_espn_article(article)
            if injury_data:
                espn_injuries.append(injury_data)

        logger.info(f"Parsed {len(espn_injuries)} injury entries from ESPN articles")

        # Fetch from NBA Official
        logger.info("Fetching injuries from NBA Official Report...")
        nba_injuries = await injury_service.fetch_nba_official_report()
        logger.info(f"Fetched {len(nba_injuries)} injuries from NBA Official Report")

        # Combine injuries
        all_injuries = espn_injuries + nba_injuries
        logger.info(f"Total injuries to ingest: {len(all_injuries)}")

        # Ingest to database
        ingested = injury_service.ingest_injuries(all_injuries)
        logger.info(f"Successfully ingested {ingested} new injuries to database")

        # Log summary
        summary = {
            "timestamp": datetime.now().isoformat(),
            "espn_articles": len(espn_articles),
            "espn_parsed": len(espn_injuries),
            "nba_official": len(nba_injuries),
            "total_ingested": ingested,
            "status": "success"
        }

        logger.info(f"Injury fetch complete: {summary}")
        return summary

    except Exception as e:
        logger.error(f"Error during injury fetch: {e}", exc_info=True)
        return {
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": str(e)
        }
    finally:
        db.close()


def parse_espn_article(article: dict) -> dict:
    """
    Parse an ESPN article for injury information.

    This is a simplified parser - production would use NLP
    to extract player names, injury types, and statuses more accurately.

    Args:
        article: ESPN article dictionary

    Returns:
        Injury data dictionary or None if no injury info found
    """
    headline = article.get("headline", "")
    description = article.get("description", "")

    combined = f"{headline} {description}".lower()

    # Check if this is an injury-related article
    injury_keywords = ["injury", "injured", "out", "questionable", "doubtful",
                      "day-to-day", "ruled out", "will not play", "will miss"]

    if not any(keyword in combined for keyword in injury_keywords):
        return None

    # Extract player name (simplified - looks for "Player Name" pattern)
    # In production, use NLP or named entity recognition
    player_name = extract_player_name_from_text(headline)

    if not player_name:
        return None

    # Extract injury type
    injury_type = extract_injury_type(combined)

    # Extract status
    status = extract_status_from_text(combined)

    return {
        "player_name": player_name,
        "injury_type": injury_type,
        "status": status,
        "description": f"{headline} - {description}",
        "source": "espn"
    }


def extract_player_name_from_text(text: str) -> str:
    """
    Extract player name from text.

    Simplified version - looks for common NBA name patterns.
    In production, use NLP with named entity recognition.
    """
    # This would need proper NLP in production
    # For now, return empty string
    return ""


def extract_injury_type(text: str) -> str:
    """Extract injury type from text."""
    text_lower = text.lower()

    injury_types = [
        "ankle", "knee", "hamstring", "concussion", "illness",
        "back", "finger", "shoulder", "foot", "hip", "heel",
        "quad", "calf", "groin", "wrist", "elbow", "rib", "eye"
    ]

    for injury_type in injury_types:
        if injury_type in text_lower:
            return injury_type

    return "unknown"


def extract_status_from_text(text: str) -> str:
    """Extract injury status from text."""
    text_lower = text.lower()

    if "out for season" in text_lower or "season-ending" in text_lower:
        return "out"
    elif "out indefinitely" in text_lower:
        return "out"
    elif "out" in text_lower and "questionable" not in text_lower:
        return "out"
    elif "doubtful" in text_lower:
        return "doubtful"
    elif "questionable" in text_lower:
        return "questionable"
    elif "day-to-day" in text_lower or "day to day" in text_lower:
        return "day-to-day"
    elif "returning" in text_lower or "activated" in text_lower:
        return "returning"
    elif "probable" in text_lower:
        return "available"
    else:
        return "questionable"


def main():
    """Entry point for the script."""
    logger.info("=" * 60)
    logger.info("Injury Fetch Script Started")
    logger.info("=" * 60)

    # Run the async fetch
    result = asyncio.run(fetch_injuries())

    # Exit with appropriate code
    if result.get("status") == "success":
        logger.info("Script completed successfully")
        sys.exit(0)
    else:
        logger.error("Script completed with errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
