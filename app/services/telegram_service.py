"""
Telegram Notification Service for sending messages via Telegram Bot.

This service provides a simple interface to send notifications via Telegram.
"""
import asyncio
import os
import json
import logging
import urllib.request
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)

# Telegram bot token (from seanbot project)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8329249261:AAEBqHMfShDgFZXJ1E57HtJYvkx5b9e4Rj4")

# Default chat ID (can be overridden via environment)
# Sean's chat ID: 5331666588
DEFAULT_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5331666588")


def get_chat_id() -> Optional[str]:
    """
    Get the chat ID from environment or try to find it from recent updates.

    Returns:
        Chat ID as string or None if not found
    """
    if DEFAULT_CHAT_ID:
        return DEFAULT_CHAT_ID

    # Try to get from recent updates
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read())
            if data.get("result"):
                chat_id = data["result"][-1]["message"]["chat"]["id"]
                logger.info(f"Found chat ID from updates: {chat_id}")
                return str(chat_id)
    except Exception as e:
        logger.warning(f"Could not get chat ID automatically: {e}")

    return None


def send_message(
    message: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML"
) -> bool:
    """
    Send a message to Telegram (synchronous version).

    Args:
        message: The message text to send
        chat_id: Optional chat ID (if not provided, will try to get from environment)
        parse_mode: Parse mode (HTML or Markdown)

    Returns:
        True if message was sent successfully, False otherwise
    """
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False

    if not chat_id:
        chat_id = get_chat_id()
        if not chat_id:
            logger.error("No chat ID available")
            return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode
    }).encode()

    try:
        with urllib.request.urlopen(url, data, timeout=10) as response:
            result = json.loads(response.read())
            if result.get("ok"):
                logger.info(f"✅ Message sent to Telegram (chat_id: {chat_id})")
                return True
            else:
                logger.error(f"Error sending message: {result}")
                return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


async def send_message_async(
    message: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML"
) -> bool:
    """
    Send a message to Telegram (async version).

    Args:
        message: The message text to send
        chat_id: Optional chat ID
        parse_mode: Parse mode (HTML or Markdown)

    Returns:
        True if message was sent successfully, False otherwise
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, send_message, message, chat_id, parse_mode)


def send_player_stats_notification(
    player_name: str,
    stats_summary: dict,
    chat_id: Optional[str] = None
) -> bool:
    """
    Send a formatted player stats notification to Telegram.

    Args:
        player_name: Name of the player
        stats_summary: Stats summary from PlayerCareerStatsService
        chat_id: Optional chat ID

    Returns:
        True if message was sent successfully
    """
    career = stats_summary.get('career_stats', {})
    last_10_avg = stats_summary.get('last_10_avg', {})
    last_10_games = stats_summary.get('last_10_games', [])

    message = f"""🏀 <b>Player Stats Update</b>

<b>{player_name}</b> ({career.get('team_abbr', 'N/A')}) - {stats_summary.get('season', '')}

📊 <b>Season Averages</b>
Points: <code>{career.get('points_per_game', 0):.1f}</code>
Rebounds: <code>{career.get('rebounds_per_game', 0):.1f}</code>
Assists: <code>{career.get('assists_per_game', 0):.1f}</code>
Threes: <code>{career.get('threes_per_game', 0):.1f}</code>

📈 <b>Last 10 Games Avg</b>
"""

    if last_10_avg:
        message += f"""Points: <code>{last_10_avg['points']:.1f}</code>
Rebounds: <code>{last_10_avg['rebounds']:.1f}</code>
Assists: <code>{last_10_avg['assists']:.1f}</code>
Threes: <code>{last_10_avg['threes']:.1f}</code>
"""
    else:
        message += "No recent games data\n"

    message += """
📅 <b>Recent Games</b>
"""

    for game in last_10_games[:5]:  # Show last 5 games
        message += f"{game.get('game_date', 'N/A')}: {game.get('points', 0)} PTS, {game.get('rebounds', 0)} REB, {game.get('assists', 0)} AST\n"

    return send_message(message.strip(), chat_id)


def send_batch_completion_notification(
    total_players: int,
    success_count: int,
    error_count: int,
    chat_id: Optional[str] = None
) -> bool:
    """
    Send a batch completion notification.

    Args:
        total_players: Total number of players processed
        success_count: Number of successful fetches
        error_count: Number of errors
        chat_id: Optional chat ID

    Returns:
        True if message was sent successfully
    """
    message = f"""✅ <b>Player Stats Sync Complete</b>

📊 Summary:
  Total: {total_players}
  ✅ Success: {success_count}
  ❌ Errors: {error_count}

Completed at: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

    return send_message(message.strip(), chat_id)
