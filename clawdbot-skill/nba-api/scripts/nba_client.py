#!/usr/bin/env python3
"""
NBA API Client for Clawdbot.
Provides commands to query the NBA Player Prop Prediction API.

Features:
- Player search by name
- Player predictions by NBA.com ID
- Game predictions
- Timeout-safe upcoming games fetch
- Top picks by confidence
"""
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
import os
from typing import Optional, Dict, Any, List

# Configuration
API_URL = os.environ.get("NBA_API_URL", "http://89.117.150.95:8001")
TIMEOUT = 30  # seconds


def api_request(endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Make HTTP request to the NBA API.

    Args:
        endpoint: API endpoint path (e.g., "/api/health")
        method: HTTP method (GET or POST)
        data: Optional data for POST requests

    Returns:
        JSON response as dictionary
    """
    url = f"{API_URL}{endpoint}"

    try:
        if method == "POST":
            # POST request with data
            post_data = json.dumps(data or {}).encode("utf-8")
            req = urllib.request.Request(url, data=post_data, method="POST")
            req.add_header("Content-Type", "application/json")
        else:
            # GET request
            req = urllib.request.Request(url)

        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return {
            "error": f"HTTP {e.code}",
            "detail": error_body
        }
    except urllib.error.URLError as e:
        return {
            "error": "Connection failed",
            "detail": str(e.reason)
        }
    except TimeoutError:
        return {
            "error": "timeout",
            "detail": f"Request timed out after {TIMEOUT}s"
        }
    except Exception as e:
        return {
            "error": "unknown",
            "detail": str(e)
        }


def format_prediction(pred: Dict[str, Any]) -> str:
    """Format a prediction for display."""
    player = pred.get("player", {})
    game = pred.get("game", {})

    rec_emoji = "📈" if pred.get("recommendation") == "OVER" else "📉"
    conf_pct = pred.get("confidence", 0) * 100
    conf_emoji = "🔥" if conf_pct >= 70 else "✅" if conf_pct >= 60 else "⚠️"

    return f"""
{player.get('name', 'Unknown')} ({player.get('team', 'N/A')})
{game.get('away_team')} @ {game.get('home_team')}

🎯 {pred.get('stat_type', 'STAT').upper()}
Predicted: {pred.get('predicted_value', 0):.1f}
Line: {pred.get('bookmaker_line', 'N/A')} ({pred.get('bookmaker_name', 'N/A')})

{rec_emoji} {pred.get('recommendation', 'N/A')} {conf_emoji}
Confidence: {conf_pct:.0f}%
""".strip()


def cmd_health() -> str:
    """Check API health status."""
    result = api_request("/api/health")

    if result.get("status") == "healthy":
        db_info = api_request("/api/data/status")
        db = db_info.get("database", {})

        return f"""🏀 API Status: Healthy
📊 Database:
   Players: {db.get('players', 0)}
   Games: {db.get('games', 0)}
   Predictions: {db.get('predictions', 0)}
   Upcoming: {db.get('upcoming_games', 0)}"""
    else:
        return f"❌ API Unhealthy: {result.get('error', 'Unknown error')}"


def cmd_search(name: str) -> str:
    """Search for players by name."""
    result = api_request(f"/api/players/search?name={urllib.parse.quote(name)}&limit=5")

    if "error" in result:
        return f"❌ Error: {result['error']} - {result.get('detail', '')}"

    players = result.get("players", [])

    if not players:
        return f"📭 No players found matching '{name}'"

    output = [f"🔍 Found {result['count']} player(s) for '{name}':\n"]

    for p in players:
        stats = p.get("stats", {})
        output.append(
            f"• {p['name']} ({p['team']}) - {p['position']}\n"
            f"  NBA ID: {p['external_id']}\n"
            f"  Predictions: {stats.get('predictions_count', 0)}"
        )

    return "\n".join(output)


def cmd_player_by_name(name: str) -> str:
    """Get player predictions by searching for player name."""
    # First, search for the player
    search_result = api_request(f"/api/players/search?name={urllib.parse.quote(name)}&limit=1")

    if "error" in search_result:
        return f"❌ Error searching for player: {search_result['error']}"

    players = search_result.get("players", [])

    if not players:
        return f"📭 Player '{name}' not found. Try a different name or check spelling."

    player = players[0]
    player_id = player["id"]
    player_name = player["name"]

    # Get predictions using database UUID
    pred_result = api_request(f"/api/predictions/player/{player_id}?limit=5")

    if "error" in pred_result:
        return f"❌ Error fetching predictions: {pred_result['error']}"

    predictions = pred_result.get("predictions", [])

    if not predictions:
        return f"📭 No predictions found for {player_name}"

    output = [f"🏀 Recent Predictions for {player_name}\n"]
    for pred in predictions:
        output.append(format_prediction(pred))
        output.append("—" * 30)

    return "\n".join(output)


def cmd_player_by_nba_id(nba_id: str) -> str:
    """
    Get player predictions by NBA.com ID.

    Users can query using NBA.com player IDs directly.
    """
    result = api_request(f"/api/predictions/player/nba/{nba_id}?limit=5")

    if "error" in result:
        return f"❌ Error: {result['error']} - {result.get('detail', '')}"

    player = result.get("player", {})
    predictions = result.get("predictions", [])

    if not predictions:
        return f"📭 No predictions found for NBA ID {nba_id} (Player: {player.get('name', 'Unknown')})"

    output = [f"🏀 Predictions for {player.get('name', 'Unknown')} (NBA ID: {nba_id})\n"]
    for pred in predictions:
        output.append(format_prediction(pred))
        output.append("—" * 30)

    return "\n".join(output)


def cmd_game(game_id: str) -> str:
    """Get predictions for a specific game."""
    result = api_request(f"/api/predictions/game/nba/{game_id}")

    if "error" in result:
        return f"❌ Error: {result['error']} - {result.get('detail', '')}"

    game = result.get("game", {})
    predictions = result.get("predictions", [])

    if not predictions:
        return f"📭 No predictions found for game {game_id}"

    output = [f"🏀 Game Predictions\n"]
    output.append(f"{game.get('away_team')} @ {game.get('home_team')}\n")
    output.append(f"Date: {game.get('date')}\n")
    output.append("—" * 30 + "\n")

    for pred in predictions:
        output.append(format_prediction(pred))
        output.append("—" * 30)

    return "\n".join(output)


def cmd_top_picks(min_confidence: float = 0.6) -> str:
    """Get high-confidence predictions."""
    result = api_request(f"/api/predictions/top?min_confidence={min_confidence}&limit=10")

    if "error" in result:
        return f"❌ Error: {result['error']}"

    predictions = result.get("predictions", [])

    if not predictions:
        return f"📭 No predictions found with confidence >= {min_confidence:.0%}"

    output = [f"🔥 Top Picks (≥{min_confidence:.0%} confidence)\n"]
    output.append("—" * 30 + "\n")

    for pred in predictions[:10]:
        output.append(format_prediction(pred))
        output.append("—" * 30)

    return "\n".join(output)


def cmd_fetch_upcoming(days: int = 7) -> str:
    """
    Fetch upcoming games from NBA.com.

    This command has timeout protection and falls back to cached data.
    """
    result = api_request("/api/data/fetch/upcoming", method="POST", data={"days_ahead": days})

    if "error" in result:
        return f"❌ Error: {result['error']} - {result.get('detail', '')}"

    fetched = result.get("games_fetched", 0)
    cached = result.get("games_cached", 0)
    errors = result.get("errors", [])

    output = [f"📅 Fetch Results:\n"]
    output.append(f"✅ Fetched from NBA.com: {fetched} games")
    output.append(f"💾 Cached from database: {cached} games")

    if errors:
        output.append(f"\n⚠️ Errors: {len(errors)}")
        for error in errors[:3]:
            output.append(f"  - {error}")

    return "\n".join(output)


def cmd_status() -> str:
    """Get database status."""
    result = api_request("/api/data/status")

    if "error" in result:
        return f"❌ Error: {result['error']}"

    db = result.get("database", {})
    status = result.get("status", "unknown")

    return f"""📊 Data Status: {status.upper()}
   Players: {db.get('players', 0)}
   Games: {db.get('games', 0)}
   Predictions: {db.get('predictions', 0)}
   Upcoming Games: {db.get('upcoming_games', 0)}
   Recent (24h): {db.get('recent_predictions_24h', 0)}"""


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: nba_client.py <command> [args]")
        print("\nCommands:")
        print("  health              - Check API status")
        print("  search <name>       - Search for players")
        print("  player <name>       - Get predictions by player name")
        print("  player_nba <id>     - Get predictions by NBA.com ID")
        print("  game <id>           - Get game predictions")
        print("  top_picks [conf]    - Get top picks (default 0.6)")
        print("  fetch_upcoming [days] - Fetch upcoming games")
        print("  status              - Get data status")
        sys.exit(1)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    try:
        if command == "health":
            print(cmd_health())
        elif command == "search" and args:
            print(cmd_search(args[0]))
        elif command == "player" and args:
            print(cmd_player_by_name(args[0]))
        elif command == "player_nba" and args:
            print(cmd_player_by_nba_id(args[0]))
        elif command == "game" and args:
            print(cmd_game(args[0]))
        elif command == "top_picks":
            confidence = float(args[0]) if args else 0.6
            print(cmd_top_picks(confidence))
        elif command == "fetch_upcoming":
            days = int(args[0]) if args else 7
            print(cmd_fetch_upcoming(days))
        elif command == "status":
            print(cmd_status())
        else:
            print(f"❌ Unknown command: {command}")
            print("Use 'nba_client.py' without arguments for usage help")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n❌ Interrupted")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
