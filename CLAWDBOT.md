# Clawdbot Telegram Integration - NBA Player Props

## Overview
Integration plan for connecting the NBA Player Prop Prediction API to Clawdbot for Telegram-based querying.

## Deployment Info
- **NBA API Base URL:** http://89.117.150.95:8001
- **Documentation:** http://89.117.150.95:8001/docs
- **Clawdbot Docs:** https://docs.clawd.bot
- **VPS:** sean-ubuntu-vps

## Skill Structure

**Location:** `~/.clawdbot/skills/nba-predictions/`

**Files:**
1. **SKILL.md** - Skill metadata and documentation
2. **nba_client.py** - Python API client with Telegram HTML formatting

## SKILL.md

```yaml
---
name: nba-predictions
description: "AI-powered NBA player prop bet predictions"
homepage: http://89.117.150.95:8001
metadata: {"clawdbot":{"emoji":"🏀","requires":{"anyBins":["python3","curl"]},"env":["NBA_API_URL"]}}
---

# NBA Player Props

Get AI-powered NBA player prop predictions via Telegram.

## Setup

1. Set API URL in environment:
   ```bash
   export NBA_API_URL="http://89.117.150.95:8001"
   ```

2. Add to ~/.clawdbot/clawdbot.json:
   ```json
   {
     "skills": {
       "entries": {
         "nba-predictions": {"enabled": true}
       }
     }
   }
   ```

3. Restart Clawdbot: `clawdbot gateway restart`

## Telegram Commands

- `/nba_health` - Check API status
- `/nba_game <game_id>` - Get predictions for a game
- `/nba_player <player_id>` - Get player predictions
- `/nba_news_recent` - Get recent news
- `/nba_news_player <name>` - Get player news
- `/nba_top_picks` - Get high-confidence predictions
```

## nba_client.py

```python
#!/usr/bin/env python3
import sys
import json
import urllib.request
import os

API_URL = os.environ.get("NBA_API_URL", "http://89.117.150.95:8001")

def fetch_json(endpoint):
    """Make HTTP request to NBA API"""
    url = f"{API_URL}{endpoint}"
    req = urllib.request.Request(url)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return {"error": str(e)}

def format_prediction_html(pred):
    """Format prediction for Telegram HTML"""
    player = pred.get("player", {})
    game = pred.get("game", {})
    rec_emoji = "📈" if pred.get("recommendation") == "OVER" else "📉"
    conf_emoji = "🔥" if pred.get("confidence", 0) >= 0.7 else "✅" if pred.get("confidence", 0) >= 0.6 else "⚠️"

    return f"""
<b>{player.get('name', 'Unknown')}</b> ({player.get('team', 'N/A')})
{game.get('away_team')} @ {game.get('home_team')}

🎯 <b>{pred.get('stat_type', 'stat').upper()}</b>
Predicted: <code>{pred.get('predicted_value', 0):.1f}</code>
Line: <code>{pred.get('bookmaker_line', 0):.1f}</code> ({pred.get('bookmaker_name', 'N/A')})

{rec_emoji} <b>{pred.get('recommendation', 'N/A')}</b> {conf_emoji}
Confidence: <code>{pred.get('confidence', 0):.0%}</code>
""".strip()

def cmd_health():
    result = fetch_json("/api/health")
    if result.get("status") == "healthy":
        models = result.get("models", {})
        status = " | ".join([f"{k}:{'✅' if v else '❌'}" for k, v in models.items()])
        return f"🏀 <b>API Status: Healthy</b>\n🤖 Models: {status}"
    return f"❌ API Unhealthy"

def cmd_game(game_id):
    result = fetch_json(f"/api/predictions/game/{game_id}")
    if "error" in result:
        return f"❌ {result['error']}"
    if not result:
        return "📭 No predictions found"
    output = [f"🏀 <b>Game Predictions</b>\n"]
    for pred in result[:10]:
        output.append(format_prediction_html(pred))
        output.append("—" * 20)
    return "\n".join(output)

def cmd_player(player_id, limit=5):
    result = fetch_json(f"/api/predictions/player/{player_id}?limit={limit}")
    if "error" in result:
        return f"❌ {result['error']}"
    if not result:
        return "📭 No predictions found"
    output = [f"🏀 <b>Recent Predictions</b>\n"]
    for pred in result:
        output.append(format_prediction_html(pred))
    return "\n".join(output)

def cmd_news_recent(limit=10):
    result = fetch_json(f"/api/news/recent?limit={limit}")
    if "error" in result:
        return f"❌ {result['error']}"
    output = ["📰 <b>Recent NBA News</b>\n"]
    for event in result[:5]:
        output.append(f"<b>{event.get('event_type', '').upper()}</b>: {event.get('headline', '')[:60]}...")
    return "\n".join(output)

def cmd_news_player(player_name, days_back=7):
    result = fetch_json(f"/api/news/player/{urllib.parse.quote(player_name)}?days_back={days_back}")
    if "error" in result:
        return f"❌ {result['error']}"
    if not result:
        return f"📭 No news for {player_name}"
    output = [f"📰 <b>News: {player_name}</b>\n"]
    for event in result:
        output.append(f"<b>{event.get('event_type', '').upper()}</b>: {event.get('headline', '')}")
    return "\n".join(output)

def main():
    if len(sys.argv) < 2:
        print("Usage: nba_client.py <command> [args]")
        sys.exit(1)
    command = sys.argv[1].lower()
    if command == "health":
        print(cmd_health())
    elif command == "game" and len(sys.argv) >= 3:
        print(cmd_game(sys.argv[2]))
    elif command == "player" and len(sys.argv) >= 3:
        print(cmd_player(sys.argv[2]))
    elif command == "news":
        print(cmd_news_recent())
    elif command == "news_player" and len(sys.argv) >= 3:
        print(cmd_news_player(sys.argv[2]))
    else:
        print(f"❌ Unknown command: {command}")

if __name__ == "__main__":
    import urllib.parse
    main()
```

## Deployment Steps

1. **Create skill directory:**
   ```bash
   mkdir -p ~/.clawdbot/skills/nba-predictions
   cd ~/.clawdbot/skills/nba-predictions
   ```

2. **Create SKILL.md** (copy from above)

3. **Create nba_client.py** (copy from above)
   ```bash
   chmod +x nba_client.py
   ```

4. **Set environment variable:**
   ```bash
   echo 'export NBA_API_URL="http://89.117.150.95:8001"' >> ~/.zshrc
   source ~/.zshrc
   ```

5. **Configure Clawdbot** - Add to ~/.clawdbot/clawdbot.json:
   ```json
   {
     "skills": {
       "entries": {
         "nba-predictions": {"enabled": true}
       }
     }
   }
   ```

6. **Restart Clawdbot:**
   ```bash
   clawdbot gateway restart
   ```

7. **Test in Telegram:**
   ```
   /nba_health
   /nba_game <game_id>
   /nba_news_recent
   ```

## Verification

1. **Test API connectivity:**
   ```bash
   curl http://89.117.150.95:8001/api/health
   ```

2. **Test Python client:**
   ```bash
   cd ~/.clawdbot/skills/nba-predictions
   python3 nba_client.py health
   ```

3. **Test Telegram commands:**
   - Send `/nba_health` to your bot
   - Verify HTML formatting renders
   - Check emoji display correctly

## Critical Files

| File | Purpose |
|------|---------|
| `~/.clawdbot/skills/nba-predictions/SKILL.md` | Skill metadata and docs |
| `~/.clawdbot/skills/nba-predictions/nba_client.py` | API client script |
| `~/.clawdbot/clawdbot.json` | Clawdbot configuration |
| `~/.zshrc` or `~/.bashrc` | Environment variables |

## Troubleshooting

**"API Unhealthy" error:**
- Check VPS: `ssh sean-ubuntu-vps "curl localhost:8001/api/health"`
- Verify network connectivity from Clawdbot host to VPS
- Check firewall rules on VPS (port 8001)

**"Module not found" error:**
- Ensure Python 3 is installed: `which python3`
- Verify urllib is available (standard library)

**Empty predictions:**
- Verify game_id exists in database
- Check predictions have been generated for that game

## Example Telegram Output

```
🏀 API Status: Healthy
🤖 Models: points:✅ | rebounds:✅ | assists:✅ | threes:✅
```

```
🏀 Game Predictions

LeBron James (LAL)
GSW @ LAL

🎯 POINTS
Predicted: 22.5
Line: 24.5 (DraftKings)

📉 UNDER ✅
Confidence: 58%
──────────────────────
```

## Future Enhancements

1. **Alert System:** Daily top picks at scheduled time
2. **Betting Tracker:** Store user bets, track ROI
3. **Player Search:** Autocomplete player names
4. **Game Reminders:** Notify before game start
5. **Confidence Filtering:** Only show predictions >70% confidence
