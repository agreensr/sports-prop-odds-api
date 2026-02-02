#!/usr/bin/env python3
"""
Generate player prop predictions for TOR vs OKC game using direct nba_api data.
Creates a 2, 3, and 5 player prop parlay.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.services.nba.player_career_stats_service import PlayerCareerStatsService
from app.services.telegram_service import send_message
from nba_api.stats.static import players
from nba_api.stats.endpoints import playergamelog

def get_team_players(team_abbr):
    """Get players for a team from nba_api."""
    all_players = players.get_players()
    # This returns all players - we need to filter by current team
    # For now, return some known key players for each team
    key_players = {
        'TOR': {
            'Scottie Barnes': 1630635,
            'RJ Barrett': 1630162,
            'Immanuel Quickley': 1630166,
            'Gradey Dick': 1641755,
        },
        'OKC': {
            'Shai Gilgeous-Alexander': 1628983,
            'Jalen Williams': 1630587,
            'Chet Holmgren': 1631120,
            'Isaiah Joe': 1630232,
        }
    }
    return key_players.get(team_abbr, {})

def get_last_10_avg(player_id, player_name):
    """Get last 10 games average for a player."""
    try:
        gamelog = playergamelog.PlayerGameLog(
            player_id=player_id,
            season='2025-26',
            season_type_all_star='Regular Season'
        )
        df = gamelog.get_data_frames()[0] if gamelog.get_data_frames() else None

        if df is None or df.empty:
            return None

        # Get last 10 games
        last_10 = df.tail(10)

        avg_pts = last_10['PTS'].mean()
        avg_reb = last_10['REB'].mean()
        avg_ast = last_10['AST'].mean()
        avg_threes = last_10['FG3M'].mean()

        return {
            'pts': round(avg_pts, 1),
            'reb': round(avg_reb, 1),
            'ast': round(avg_ast, 1),
            'threes': round(avg_threes, 1)
        }
    except Exception as e:
        print(f"Error fetching gamelog for {player_name}: {e}")
        return None

def generate_prop_picks(stats, player_name, prop_type, line):
    """Generate a prop pick recommendation."""
    if not stats:
        return None

    stat_value = stats.get(prop_type.lower(), 0)

    # Simple logic: if avg is 10% higher than line, recommend OVER
    if stat_value >= line * 1.1:
        return {
            'player': player_name,
            'stat': prop_type.upper(),
            'predicted': stat_value,
            'line': line,
            'recommendation': 'OVER',
            'confidence': min(0.90, 0.60 + (stat_value - line) / line * 0.3)
        }
    elif stat_value <= line * 0.9:
        return {
            'player': player_name,
            'stat': prop_type.upper(),
            'predicted': stat_value,
            'line': line,
            'recommendation': 'UNDER',
            'confidence': min(0.90, 0.60 + (line - stat_value) / line * 0.3)
        }
    return None

def main():
    # Key players for TOR and OKC
    tor_players = {
        'Scottie Barnes': 1630567,
        'RJ Barrett': 1629628,
        'Immanuel Quickley': 1630193,
        'Gradey Dick': 1641755,
    }

    okc_players = {
        'Shai Gilgeous-Alexander': 1628983,
        'Jalen Williams': 1631114,
        'Chet Holmgren': 1631096,
        'Isaiah Joe': 1630232,
    }

    # Prop lines (example - these would come from actual sportsbook)
    prop_lines = {
        'Shai Gilgeous-Alexander': {'PTS': 30.5, 'AST': 5.5, 'REB': 5.5},
        'Jalen Williams': {'PTS': 19.5, 'REB': 4.5, 'AST': 4.5},
        'Chet Holmgren': {'PTS': 16.5, 'REB': 8.5, 'AST': 2.5},
        'Scottie Barnes': {'PTS': 20.5, 'REB': 7.5, 'AST': 5.5},
        'RJ Barrett': {'PTS': 18.5, 'REB': 5.5, 'AST': 3.5},
        'Immanuel Quickley': {'PTS': 16.5, 'AST': 4.5, 'REB': 3.5},
        'Isaiah Joe': {'PTS': 12.5, 'THREES': 2.5},
        'Gradey Dick': {'PTS': 11.5, 'THREES': 2.5},
    }

    all_picks = []

    # Get stats for all players
    print("Fetching player stats...")

    for player_name, player_id in {**tor_players, **okc_players}.items():
        stats = get_last_10_avg(player_id, player_name)

        if stats and player_name in prop_lines:
            lines = prop_lines[player_name]

            for stat_type, line in lines.items():
                pick = generate_prop_picks(stats, player_name, stat_type, line)
                if pick and pick['confidence'] >= 0.55:
                    all_picks.append(pick)

    # Sort by confidence
    all_picks.sort(key=lambda x: x['confidence'], reverse=True)

    # Create message
    message = """🏀 <b>TOR vs OKC Player Props</b>
📅 January 25, 2026

<b>Top Picks (Last 10 Games Avg):</b>
"""

    for i, pick in enumerate(all_picks[:10], 1):
        rec_emoji = "📈" if pick['recommendation'] == "OVER" else "📉"
        conf_pct = pick['confidence'] * 100

        message += f"""
{i}. {rec_emoji} <b>{pick['player']}</b>
   <b>{pick['stat']}</b>
   Avg: <code>{pick['predicted']}</code>
   Line: <code>{pick['line']}</code>
   <b>{pick['recommendation']}</b> (Conf: <code>{conf_pct:.0f}%</code>)
"""

    # Create parlays
    if len(all_picks) >= 2:
        message += """

━━━━━━━━━━━━━━━━━━━━━━

<b>🎯 Recommended Parlays:</b>

<b>2-Leg Parlay:</b>
"""
        for i in range(2):
            p = all_picks[i]
            message += f"  • {p['player']} {p['stat']} {p['recommendation']} {p['line']}\n"

    if len(all_picks) >= 3:
        message += "\n<b>3-Leg Parlay:</b>\n"
        for i in range(3):
            p = all_picks[i]
            message += f"  • {p['player']} {p['stat']} {p['recommendation']} {p['line']}\n"

    if len(all_picks) >= 5:
        message += "\n<b>5-Leg Parlay:</b>\n"
        for i in range(5):
            p = all_picks[i]
            message += f"  • {p['player']} {p['stat']} {p['recommendation']} {p['line']}\n"

    message += """

━━━━━━━━━━━━━━━━━━━━━━

<i>⚠️ These picks are based on last 10 games average. Always check actual sportsbook lines before betting.</i>
"""

    print("Sending to Telegram...")
    send_message(message.strip())
    print("✅ Done!")

if __name__ == "__main__":
    main()
