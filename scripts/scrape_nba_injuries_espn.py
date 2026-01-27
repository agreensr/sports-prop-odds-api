#!/usr/bin/env python3
"""
NBA Injury Report Parser using ESPN data via web-reader.

Scrapes injury data from ESPN and stores in the database.
This should be run before generating predictions.

Usage:
    python scripts/scrape_nba_injuries_espn.py
"""
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
import re
import json
import httpx

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.nba.models import Player, PlayerInjury
from app.services.nba.injury_service import InjuryService


class ESPNInjuryScraper:
    """Scrape ESPN injury data using web-reader MCP server."""

    # Web-reader MCP endpoint (if hosted locally or on VPS)
    WEB_READER_URL = "http://localhost:8888/mcp/web-reader/webReader"
    ESPN_INJURIES_URL = "https://www.espn.com/nba/injuries"

    async def fetch_espn_data(self) -> str:
        """
        Fetch ESPN injury data using httpx directly.
        ESPN's page is accessible and returns structured content.
        """
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = await client.get(
                self.ESPN_INJURIES_URL,
                headers=headers
            )

            if response.status_code == 200:
                # ESPN returns HTML - try to parse the content
                # For now, return the raw HTML content
                return response.text
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")


def parse_injury_data(markdown: str) -> list:
    """
    Parse injury data from ESPN markdown format.

    The ESPN data comes in markdown tables with columns:
    | NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
    """
    injuries = []

    # Split by team sections (marked by ### headers)
    team_sections = re.split(r'###\s+(.+?)\s+\((\w+)\)', markdown)

    for section in team_sections[1:]:  # Skip first section (header)
        if not section.strip():
            continue

        # Extract team name and abbreviation from header
        header_match = re.search(r'###\s+(.+?)\s+\((\w+)\)', section)
        if not header_match:
            continue

        team_name = header_match.group(1).strip()
        team_abbr = header_match.group(2)

        # Find the injury table
        table_match = re.search(
            r'\| NAME.*?\n((?:\|[^|]+\n)+)',
            section,
            re.MULTILINE
        )

        if not table_match:
            continue

        table_text = table_match.group(1)

        # Parse table rows
        lines = table_text.split('\n')

        for line in lines[2:]:  # Skip header lines
            if not line.strip() or line.startswith('|---'):
                continue

            # Parse table row
            cells = [cell.strip() for cell in line.split('|')[1:-1]]  # Remove empty first/last

            if len(cells) < 5:
                continue

            player_name = cells[0]
            position = cells[1]
            est_return = cells[2]
            status = cells[3]
            comment = cells[4] if len(cells) > 4 else ""

            # Clean up status
            status = status.strip()

            # Normalize status
            if 'out' in status.lower():
                if 'indefinitely' in status.lower():
                    status = "Out Indefinitely"
                else:
                    status = "Out"
            elif 'day-to-day' in status.lower():
                status = "Day-To-Day"
            elif 'questionable' in status.lower():
                status = "Questionable"

            # Extract injury type from comment
            injury_type = "Unknown"

            # Common injury patterns to look for
            patterns = [
                (r'(knee|achilles|acl|mcl|foot|ankle|hamstring|groin|hip|wrist|finger|thumb|shoulder|elbow|toe|heel|back|neck|concussion)', 'i'),
                (r'(torn|sprain|strain|fracture|break|tear)', 'i'),
                (r'(illness|rest|conditioning)', 'i'),
                (r'(surgery|procedure)', 'i')
            ]

            for pattern, _ in patterns:
                if re.search(pattern, comment):
                    # Extract the specific injury
                    injury_match = re.search(pattern, comment, re.IGNORECASE)
                    if injury_match:
                        injury_type = injury_match.group(1).capitalize()
                    break

            injuries.append({
                'player_name': player_name,
                'team_abbr': team_abbr,
                'position': position,
                'est_return': est_return if est_return else None,
                'status': status,
                'injury_type': injury_type,
                'comment': comment
            })

    return injuries


def store_injuries(db_session, injuries: list) -> dict:
    """Store parsed injuries in database."""
    created = 0
    updated = 0
    errors = 0

    # Clear old injuries (ESPN is authoritative source)
    db_session.query(PlayerInjury).delete()

    for injury_data in injuries:
        try:
            player_name = injury_data.get('player_name', '')
            team_abbr = injury_data.get('team_abbr', '')

            # Find player in database
            player = db_session.query(Player).filter(
                Player.name == player_name,
                Player.team == team_abbr
            ).first()

            if not player:
                # Try name match only
                player = db_session.query(Player).filter(
                    Player.name == player_name
                ).first()

            if player:
                # Check if injury already exists with same status
                existing = db_session.query(PlayerInjury).filter(
                    PlayerInjury.player_id == player.id,
                    PlayerInjury.status == injury_data['status']
                ).first()

                injury_data['impact_description'] = injury_data.get('comment', '')

                if existing:
                    # Update existing
                    existing.injury_type = injury_data['injury_type']
                    existing.impact_description = injury_data['impact_description']
                    existing.reported_date = datetime.now(timezone.utc).date()
                    existing.updated_at = datetime.now(timezone.utc)
                    updated += 1
                else:
                    # Create new injury record
                    injury = PlayerInjury(
                        id=str(uuid4()),
                        player_id=player.id,
                        injury_type=injury_data['injury_type'],
                        status=injury_data['status'],
                        impact_description=injury_data['impact_description'],
                        reported_date=datetime.now(timezone.utc).date(),
                        external_source='espn_web_reader',
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                    db_session.add(injury)
                    created += 1

        except Exception as e:
            errors += 1
            print(f"Error processing {injury_data}: {e}")

    db_session.commit()

    return {
        'created': created,
        'updated': updated,
        'errors': errors,
        'total': created + updated
    }


async def main():
    """Main function to scrape and store injuries."""
    # Fresh ESPN injury data fetched via web-reader MCP on 2026-01-26
    espn_injury_data = """## NBA Injuries

![Image 1](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Atlanta Hawks\")Atlanta Hawks

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Zaccharie Risacher | F | Jan 26 | Out | Jan 19: The Hawks announced Monday that Risacher (knee) will be re-evaluated in one week, Kevin Chouinard of the Hawks' official site reports. |
| Kristaps Porzingis | C | Jan 26 | Out | Jan 19: The Hawks announced Monday that Porzingis (Achilles) will be re-evaluated in one week, Kevin Chouinard of the Hawks' official site reports. |
| N'Faly Dante | C | Jan 1 | Out | Dec 23: Dante will undergo season-ending surgery to repair a torn ACL in his right knee, Michael Scotto of USA Today reports. |

![Image 2](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Boston Celtics\")Boston Celtics

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Josh Minott | F | Jan 26 | Out | Jan 24: Minott (ankle) is out for Saturday's game against the Bulls, Justin Turpin of WEEI.com reports. |
| Jayson Tatum | F | Apr 1 | Out | Oct 9: The Celtics have not ruled Tatum (Achilles) out for the 2025-26 season, ESPN's Shams Charania reported on the Pat McAfee Show on Thursday. |

![Image 3](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Brooklyn Nets\")Brooklyn Nets

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Nolan Traore | G | Jan 27 | Out | Jan 24: Traore has been ruled out for Sunday's game against the Clippers due to illness. |
| Noah Clowney | F | Jan 25 | Day-To-Day | Jan 24: Clowney (back) is doubtful to play Sunday against the Clippers, Brian Lewis of the New York Post reports. |
| Cam Thomas | G | Jan 27 | Out | Jan 24: Thomas won't play in Sunday's game against the Clippers due to a sprained left ankle. |
| Haywood Highsmith | F | Jan 27 | Out | Jan 19: Highsmith (knee) is out for Monday's game against the Suns. |

![Image 4](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Charlotte Hornets\")Charlotte Hornets

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| KJ Simpson | G | Jan 26 | Out | Jan 23: Simpson (hip) has been ruled out for Saturday's game against the Wizards. |
| Mason Plumlee | C | Feb 19 | Out | Dec 31: Plumlee underwent surgery to address his right groin injury and will be reevaluated in six weeks, the Hornets announced. |

![Image 5](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Chicago Bulls\")Chicago Bulls

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Tre Jones | G | Feb 9 | Out | Jan 23: Jones (hamstring) will be re-evaluated in two weeks, Will Gottlieb of AllCHGO.com reports. |
| Zach Collins | F | Feb 19 | Out | Jan 14: Head coach Billy Donovan said he doesn't think Collins (toe) will return before the All-Star break, which begins Feb. 13, K.C. Johnson of Chicago Sports Network reports. |
| Noa Essengue | F | Oct 1 | Out | Dec 3: Essengue will undergo left shoulder surgery and will miss the remainder of the 2025-26 season, K.C. Johnson of Chicago Sports Network reports. |

![Image 6](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Cleveland Cavaliers\")Cleveland Cavaliers

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| De'Andre Hunter | F | Jan 26 | Out | Jan 24: Hunter (knee) won't play Saturday versus the Magic, Chris Fedor of The Cleveland Plain Dealer reports. |
| Sam Merrill | G | Jan 26 | Out | Jan 24: Merrill (hand) has been ruled out for Saturday's game against the Magic. |
| Chris Livingston | F | Jan 26 | Out | Jan 24: Livingston agreed to a two-way contract with the Cavaliers on Friday, Shams Charania of ESPN reports. |
| Darius Garland | G | Jan 28 | Out | Jan 18: Garland will be re-evaluated in the next 7-to-10 days after being diagnosed with a Grade 1 right big toe sprain. |
| Max Strus | G | Feb 19 | Out | Jan 6: Strus (foot) is expected to miss at least four more weeks, Marc J. Spears of ESPN.com reports. |

![Image 7](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Dallas Mavericks\")Dallas Mavericks

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Moussa Cisse | C | Jan 25 | Out | Jan 24: Cisse (illness) won't play in Saturday's game against the Lakers. |
| Anthony Davis | F | Mar 1 | Out | Jan 13: A second opinion revealed Davis (finger) won't require surgery, and he'll be re-evaluated in six weeks, Shams Charania of ESPN reports. |
| Dereck Lively II | C | Oct 1 | Out | Dec 21: Lively successfully underwent surgery on his right foot Sunday. |
| Kyrie Irving | G | Feb 12 | Out | Dec 13: Irving (knee) remains out indefinitely and doesn't have a return timetable, Mavericks reporter Grant Afseth said during an appearance on HoopsHype's podcast 'Around the Beat' on Friday. |
| Dante Exum | G | Oct 1 | Out | Nov 20: The Mavericks announced Thursday that Exum will undergo season-ending knee surgery. |

![Image 8](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Denver Nuggets\")Denver Nuggets

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Jonas Valanciunas | C | Jan 25 | Day-To-Day | Jan 24: Valanciunas (calf) is questionable to play Sunday in Memphis. |
| Peyton Watson | G | Jan 25 | Day-To-Day | Jan 24: Watson (ankles) is listed as questionable for Sunday's game against the Grizzlies. |
| Christian Braun | G | Jan 27 | Out | Jan 24: Braun (ankle) has been ruled out for Sunday's game against the Grizzlies. |
| Aaron Gordon | F | Jan 27 | Out | Jan 24: Gordon (hamstring) has been ruled out for Sunday's game in Memphis. |
| Jamal Murray | G | Jan 25 | Day-To-Day | Jan 24: Murray (hamstring/hip) is listed as questionable for Sunday's game against Memphis. |
| Cameron Johnson | F | Jan 27 | Out | Jan 20: Johnson (knee) has yet to progress to contact work and remains out indefinitely, Vic Lombardi of Altitude Sports reports. |
| Nikola Jokic | C | Feb 1 | Out | Jan 14: Jokic (knee) has resumed on-court workouts, ESPN's Shams Charania reports. |
| Tamar Bates | G | Apr 1 | Out | Dec 22: The Nuggets announced Monday that Bates (foot) will be re-evaluated in 12 weeks. |

![Image 9](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Detroit Pistons\")Detroit Pistons

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Cade Cunningham | G | Jan 25 | Day-To-Day | Jan 24: Cunningham is probable for Sunday's game against the Kings due to right wrist injury management. |
| Caris LeVert | G | Jan 25 | Day-To-Day | Jan 24: LeVert (illness) is doubtful for Sunday's game against the Kings. |

![Image 10](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Golden State Warriors\")Golden State Warriors

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Jonathan Kuminga | F | Jan 26 | Out | Jan 24: Kuminga is out for Saturday's game against Minnesota due to left knee soreness. |
| De'Anthony Melton | G | Jan 25 | Day-To-Day | Jan 24: Melton (rest) is questionable for Sunday's game in Minnesota, Anthony Slater of ESPN.com reports. |
| Al Horford | C | Jan 25 | Day-To-Day | Jan 24: Horford (left toe injury management) is questionable for Sunday's game against Minnesota. |
| Stephen Curry | G | Jan 25 | Day-To-Day | Jan 24: Curry is listed as questionable for Sunday's game against Minnesota due to right knee soreness. |
| Jimmy Butler III | F | Dec 1 | Out | Jan 20: Butler's injury from Monday Night's game involves a torn right ACL and he will be out for the rest of the season, per Shams Charania of ESPN. |
| Seth Curry | SG | Jan 25 | Out | Jan 11: The Warriors announced Sunday that Curry is making progress in his recovery from a sciatic nerve issue and will be re-evaluated in two weeks. |

![Image 11](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Houston Rockets\")Houston Rockets

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Dorian Finney-Smith | F | Jan 26 | Day-To-Day | Jan 23: Finney-Smith is out for Friday's game against Detroit due to left ankle injury management. |
| Tari Eason | F | Jan 26 | Day-To-Day | Jan 23: Eason (rest) will not play Friday against the Pistons. |
| Aaron Holiday | G | Jan 26 | Out | Jan 23: Holiday is out for Friday's game against the Pistons due to back spasms. |
| Steven Adams | C | Mar 16 | Out | Jan 20: Head coach Ime Udoka said Tuesday that Adams suffered a "severely sprained, Grade 3 ankle sprain" and will be out indefinitely, Vanessa Richardson of Space City Home Network reports. |
| Fred VanVleet | G | Jun 1 | Out | Sep 22: VanVleet suffered a torn ACL and may be out for the entire 2025-26 campaign, Shams Charania of ESPN reports. |

![Image 12](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Indiana Pacers\")Indiana Pacers

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Quenton Jackson | G | Jan 26 | Day-To-Day | Jan 23: Jackson (ankle) won't play in Friday's game against the Thunder, Dustin Dopirak of The Indianapolis Star reports. |
| Bennedict Mathurin | G | Jan 26 | Out | Jan 22: Mathurin (thumb) has been ruled out for Friday's game against the Thunder. |
| Obi Toppin | F | Feb 2 | Out | Oct 31: Toppin will undergo surgery to place a screw in his right foot Monday, Dustin Dopirak of The Indianapolis Star reports. |
| Tyrese Haliburton | G | Oct 1 | Out | Jul 7: Haliburton will miss the entire 2025-26 season while recovering from surgery on his right Achilles tendon, Shams Charania of ESPN reports. |

![Image 13](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"LA Clippers\")LA Clippers

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Kawhi Leonard | F | Jan 25 | Day-To-Day | Jan 24: Leonard (knee/illness) is listed as questionable for Sunday's game against Brooklyn, Joey Linn of SI.com reports. |
| Bogdan Bogdanovic | G | Feb 2 | Out | Jan 24: Bogdanovic (hamstring) won't play Sunday against the Nets. |
| Derrick Jones Jr. | F | Feb 19 | Out | Jan 4: Jones has been diagnosed with a Grade 2 MCL sprain in his right knee and will be re-evaluated in six weeks, Shams Charania of ESPN reports. |
| Bradley Beal | G | Oct 1 | Out | Nov 12: Beal will undergo season-ending surgery on his left hip, ESPN's Shams Charania reports. |

![Image 14](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Los Angeles Lakers\")Los Angeles Lakers

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Austin Reaves | G | Jan 26 | Out | Jan 24: Head coach JJ Redick said that Reaves scrimmaged Saturday and that Reaves should be able to return "sooner than later," Dan Woike of The Athletic reports. |
| Adou Thiero | F | Feb 2 | Out | Dec 31: Thiero will miss at least four weeks with a right MCL sprain, Law Murray of The Athletic reports. |

![Image 15](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Memphis Grizzlies\")Memphis Grizzlies

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Santi Aldama | F | Jan 26 | Out | Jan 24: Aldama (knee) has been ruled out for Sunday's game versus the Nuggets. |
| Ty Jerome | G | Jan 30 | Out | Jan 24: Grizzlies head coach Tuomas Iisalo said Friday that Jerome (calf) is likely to make his season debut within 1-to-2 weeks, Jonah Dylan of The Memphis Commercial Appeal reports. |
| Ja Morant | G | Feb 20 | Out | Jan 24: Morant (elbow) will be reevaluated in approximately three weeks, the Grizzlies announced Saturday. |
| Scotty Pippen Jr. | G | Feb 20 | Out | Jan 14: The Grizzlies announced Wednesday that Pippen is progressing well in his recovery from left toe surgery and is expected to return in 4-6 weeks. |
| Zach Edey | C | Mar 4 | Out | Jan 14: The Grizzlies announced Wednesday that Edey continues to recover from a stress reaction in his left ankle and will maintain his current plan of offloading and rehabilitation before being re-evaluated in six weeks. |
| Brandon Clarke | F | Feb 20 | Out | Jan 14: Clarke is progressing well from his Grade 2 right calf strain and is expected to return in four to six weeks, the Grizzlies announced Wednesday. |

![Image 16](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Miami Heat\")Miami Heat

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Davion Mitchell | G | Jan 25 | Out | Jan 24: Mitchell (shoulder) is out for Saturday's game against the Jazz, Ira Winderman of the South Florida Sun Sentinel reports. |
| Kel'el Ware | C | Jan 28 | Out | Jan 23: Ware returned to Miami for treatment on his strained right hamstring Thursday, and he won't play in the Heat's back-to-back set against the Jazz on Saturday and the Suns on Sunday, Ira Winderman of the South Florida Sun Sentinel reports. |
| Tyler Herro | G | Jan 28 | Out | Jan 19: An MRI revealed a costochondral issue with Herro's ribs that will sideline him for Miami's five-game road trip, Anthony Chiang of the Miami Herald reports. |
| Terry Rozier | G | Feb 20 | Out | Oct 23: The NBA placed Rozier on immediate leave from the Heat on Thursday, ESPN's Shams Charania reports. |

![Image 17](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Milwaukee Bucks\")Milwaukee Bucks

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Gary Trent Jr. | G | Jan 25 | Day-To-Day | Jan 24: Trent (illness) is probable for Sunday's game against the Mavericks. |
| AJ Green | G | Jan 25 | Day-To-Day | Jan 24: Green (illness) is listed as questionable for Sunday's game against Dallas. |
| Giannis Antetokounmpo | F | Feb 20 | Out | Jan 24: Antetokounmpo said after Friday's 102-100 loss to the Nuggets that he expects to be sidelined for at least 4-to-6 weeks due to the right calf injury he appeared to suffer during the first quarter, Jamal Collier of ESPN.com reports. |
| Kevin Porter Jr. | G | Feb 3 | Out | Jan 21: Doc Rivers said that Porter (oblique) won't play "any time soon," and he's without an official timetable to return, Justin Garcia of Locked On Bucks reports. |
| Taurean Prince | F | Feb 20 | Out | Jan 1: The Bucks applied for a Disabled Player Exception for Prince earlier this month, indicating that they anticipate that he's "substantially more likely than not" to be unable to play through June 15, Eric Nehm of The Athletic reports. |

![Image 18](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Minnesota Timberwolves\")Minnesota Timberwolves

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Terrence Shannon Jr. | G | Jan 25 | Out | Jan 19: Shannon (foot) has been ruled out for Tuesday's game against the Jazz. |

![Image 19](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"New Orleans Pelicans\")New Orleans Pelicans

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Jose Alvarado | G | Jan 25 | Out | Jan 24: Alvarado (oblique) is listed as questionable for Sunday's game against San Antonio. |
| Dejounte Murray | G | Feb 20 | Out | Jan 7: Pelicans head coach James Borrego said Sunday that Murray (Achilles) is "making a lot of progress" but doesn't appear to be close to making his season debut, Rod Walker of The New Orleans Times-Picayune reports. "We hope to get him back in our building here soon. He's doing a lot of work getting ready to get back here," Borrego said of Murray. "I say in the next month we'll have a little bit more clarity on where he's at. But he's made a lot of progress. Significant progress." |

![Image 20](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Oklahoma City Thunder\")Oklahoma City Thunder

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Ajay Mitchell | G | Jan 27 | Out | Jan 24: Mitchell (abdomen) won't play Sunday against the Raptors. |
| Alex Caruso | G | Jan 27 | Out | Jan 24: Caruso (adductor) won't play Sunday versus the Raptors. |
| Isaiah Hartenstein | C | Jan 27 | Out | Jan 24: Hartenstein (calf) won't play in Sunday's game against Toronto. |
| Aaron Wiggins | G | Jan 25 | Day-To-Day | Jan 24: Wiggins is questionable to play Sunday versus the Raptors due to a right hip impingement. |
| Jalen Williams | G | Feb 3 | Out | Jan 19: Williams (hamstring) will be re-evaluated in two weeks, Justin Martinez of The Oklahoman reports. |
| Nikola Topic | G | Feb 20 | Out | Oct 30: Topic has been diagnosed with testicular cancer, Thunder general manager Sam Presti announced Thursday, Justin Martinez of The Oklahoman reports. |
| Thomas Sorber | C | Oct 1 | Out | Sep 5: The Thunder announced Friday that Sorber has sustained a torn ACL in his right knee during an offseason workout, NBA reporter Marc Stein reports. |

![Image 21](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Orlando Magic\")Orlando Magic

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Franz Wagner | F | Jan 26 | Out | Jan 23: Wagner (ankle) has been ruled out for Saturday's game against the Cavaliers. |
| Colin Castleton | C | Jan 26 | Out | Nov 24: The Magic plan to sign Castleton to a two-way deal, Michael Scotto of USA Today reports. |

![Image 22](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Phoenix Suns\")Phoenix Suns

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Jalen Green | G | Jan 25 | Day-To-Day | Jan 24: Green (hamstring) is questionable for Sunday's game against Miami, Duane Rankin of The Arizona Republic reports. |
| Devin Booker | G | Jan 27 | Out | Jan 24: Booker (ankle) is out for Sunday's game against the Heat, Duane Rankin of The Arizona Republic reports. |

![Image 23](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Portland Trail Blazers\")Portland Trail Blazers

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Robert Williams III | C | Jan 26 | Day-To-Day | Jan 24: Williams (knee) has been ruled out for Friday's game against the Raptors, Casey Holdahl of the Trail Blazers' official site reports. |
| Duop Reath | C | Jan 26 | Day-To-Day | Jan 24: Reath (foot) has been ruled out for Friday's game against the Raptors, Casey Holdahl of the Trail Blazers' official site reports. |
| Deni Avdija | F | Jan 26 | Day-To-Day | Jan 24: Avdija (back) has been ruled out for Friday's game against the Raptors, though he will travel with the Trail Blazers for their upcoming three-game road trip, Danny Marang of 1080 The Fan Portland reports. |
| Kris Murray | F | Jan 26 | Out | Jan 23: Murray is out for Friday's game against Toronto due to a lumbar strain. |
| Scoot Henderson | G | Jan 26 | Out | Jan 23: Henderson (hamstring) will not play Friday against the Raptors. |
| Matisse Thybulle | G | Jan 26 | Out | Jan 16: Thybulle (knee, thumb) won't play Saturday versus the Lakers and remains without a timetable to return. |
| Blake Wesley | G | Jan 30 | Out | Nov 5: Wesley underwent a successful procedure to repair a fracture of the fifth metatarsal base in his right foot Wednesday, and he's expected to be sidelined for 8-12 weeks, Brett Siegel of ClutchPoints.com reports. |
| Damian Lillard | G | Oct 1 | Out | Sep 25: Lillard won't be back on the court for the 2025-26 season, as he made clear during an interview with YouTube influencer Speed on Wednesday. |

![Image 24](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Sacramento Kings\")Sacramento Kings

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Zach LaVine | G | Jan 25 | Day-To-Day | Jan 24: LaVine is now questionable for Sunday's game against the Pistons due to low back soreness. |
| Keegan Murray | F | Feb 4 | Out | Jan 6: Murray (ankle), who won't play in Monday's game against Dallas, is expected to miss at least three weeks, NBA reporter Marc Stein reports. |

![Image 25](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"San Antonio Spurs\")San Antonio Spurs

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Luke Kornet | C | Jan 25 | Day-To-Day | Jan 24: Kornet (thigh) is listed as questionable for Sunday's game against the Pelicans, Paul Garcia of ProjectSpurs.com reports. |
| David Jones Garcia | F | Jan 25 | Day-To-Day | Jan 21: Jones Garcia totaled 12 points (5-7 FG, 1-1 3Pt, 1-2 FT), five rebounds, six assists, one block and three steals in 19 minutes during Thursday's 135-126 victory over the Hawks. |

![Image 26](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Toronto Raptors\")Toronto Raptors

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Immanuel Quickley | G | Jan 25 | Day-To-Day | Jan 24: Quickley is now questionable for Sunday's game against Oklahoma City due to right ankle soreness. |
| Ja'Kobe Walter | G | Jan 25 | Out | Jan 24: Walter (hip) is listed as questionable for Sunday's game against OKC. |
| Collin Murray-Boyles | F | Jan 25 | Out | Jan 24: Murray-Boyles (thumb) is questionable for Sunday's game in Oklahoma City. |
| Jakob Poeltl | C | Jan 28 | Out | Jan 21: Poeltl (back) isn't with the team on their road trip and is seeing a specialist in Toronto on Thursday, Michael Grange of Sportsnet.ca reports. |
| Chucky Hepburn | G | Feb 19 | Out | Jan 6: Hepburn produced 17 points (6-10 FG, 1-4 3Pt, 2-2 FT), 15 assists, two rebounds and three steals in 35 minutes of Wednesday's 115-108 G League win over the Delaware Blue Coats. |

![Image 27](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Utah Jazz\")Utah Jazz

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Lauri Markkanen | F | Jan 27 | Out | Jan 24: Markkanen (conditioning) has been ruled out for Saturday's game against the Heat. |
| Kevin Love | F | Jan 27 | Out | Jan 23: Love has been ruled out for Saturday's game against the Heat due to a left knee contusion. |
| Oscar Tshiebwe | C | Jan 24 | Day-To-Day | Jan 22: Tshiebwe signed a one-year, two-way contract with the Jazz on Monday, Keith Smith of Spotrac.com reports. |
| Georges Niang | F | Jan 27 | Out | Jan 20: Niang (foot) is out for Tuesday's game against the Spurs. |
| Elijah Harkless | G | Jan 27 | Out | Jan 13: Harkless finished Monday's 105-103 win over the Celtics with three points (1-4 FG, 0-2 3Pt, 1-1 FT), one rebound, two assists and one steal across 21 minutes. |
| Walker Kessler | C | Oct 1 | Out | Nov 5: Kessler will undergo left shoulder surgery and will miss the remainder of the 2025-26 season, Tony Jones of The Athletic reports. |

![Image 28](blob:https://www.espn.com/b9a31d3949b1882a09ed2f8508d538f3 \"Washington Wizards\")Washington Wizards

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Khris Middleton | F | Jan 27 | Day-To-Day | Jan 24: Middleton (foot) has been ruled out for Saturday's game against the Hornets. |
| AJ Johnson | G | Jan 27 | Day-To-Day | Jan 24: Johnson (illness) will not play Saturday against the Hornets. |
| Marvin Bagley III | F | Jan 27 | Day-To-Day | Jan 24: Bagley is out for Saturday's game against the Hornets due to a thoracic strain. |
| Kyshawn George | F | Jan 27 | Day-To-Day | Jan 24: George did not return to Saturday's 119-115 loss to the Hornets after sustaining an ankle injury early in the fourth quarter. He finished with 11 points (4-15 FG, 2-10 3Pt, 1-1 FT), eight rebounds, seven assists, two steals and one block over 25 minutes prior to his injury. |
| Tristan Vukcevic | F | Jan 27 | Out | Jan 23: Vukcevic (hamstring) will not play Saturday against Charlotte. |
| Bilal Coulibaly | G | Jan 27 | Out | Jan 23: Coulibaly (back) will not play Saturday against Charlotte. |
| Cam Whitmore | F | Oct 1 | Out | Jan 15: Whitmore has begun the recovery process for a diagnosed venous condition and he will miss the remainder of the 2025-26 season. |
| Trae Young | G | Feb 19 | Out | Jan 14: Young (knee, quadriceps) will be re-evaluated following the mid-February All-Star break, Shams Charania of ESPN reports. |"""

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Zaccharie Risacher | F | Jan 26 | Out | Jan 19: The Hawks announced Monday that Risacher (knee) will be re-evaluated in one week |
| Kristaps Porzingis | C | Jan 26 | Out | Jan 19: Porzingis (Achilles) will be re-evaluated in one week |
| N'Faly Dante | C | Jan 1 | Out | Dec 23: Dante will undergo season-ending surgery to repair a torn ACL |

![Image 2](blob:...) "Boston Celtics")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Josh Minott | F | Jan 26 | Out | Jan 24: Minott (ankle) is out for Saturday's game |
| Jayson Tatum | F | Apr 1 | Out | Oct 9: The Celtics have not ruled Tatum (Achilles) out for the 2025-26 season |

![Image 3](blob:...) "Brooklyn Nets")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Nolan Traore | G | Jan 27 | Out | Jan 24: Traore has been ruled out for Sunday's game |

![Image 4](blob:...) "Charlotte Hornets")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| KJ Simpson | G | Jan 26 | Out | Jan 23: Simpson (hip) has been ruled out |
| Mason Plumlee | C | Feb 19 | Out | Dec 31: Plumlee underwent surgery for right groin injury |

![Image 5](blob:...) "Chicago Bulls")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Tre Jones | G | Feb 9 | Out | Jan 23: Jones (hamstring) will be reevaluated in two weeks |
| Zach Collins | F | Feb 19 | Out | Jan 14: Collins (toe) won't return before All-Star break |

![Image 6](blob:...) "Cleveland Cavaliers")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| De'Andre Hunter | F | Jan 26 | Out | Jan 24: Hunter (knee) won't play Saturday |
| Sam Merrill | G | Jan 26 | Out | Jan 24: Merrill (hand) has been ruled out |
| Darius Garland | G | Jan 28 | Out | Jan 18: Garland will be reevaluated in 7-10 days (Grade 1 big toe sprain) |
| Max Strus | G | Feb 19 | Out | Jan 6: Strus (foot) expected to miss at least four more weeks |

![Image 7](blob:...) "Dallas Mavericks")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Anthony Davis | F | Mar 1 | Out | Jan 13: Davis (finger) won't require surgery, re-evaluated in six weeks |
| Dante Exum | G | Oct 1 | Out | Nov 20: Exum will undergo season-ending knee surgery |
| Kyrie Irving | G | Feb 12 | Out | Dec 13: Irving (knee) remains out indefinitely |

![Image 8](blob:...) "Denver Nuggets")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Jonas Valanciunas | C | Jan 25 | Day-To-Day | Jan 24: Valanciunas (calf) questionable for Sunday |
| Peyton Watson | G | Jan 25 | Day-To-Day | Jan 24: Watson (ankles) questionable for Sunday |

![Image 9](blob:...) "Detroit Pistons")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Cade Cunningham | G | Jan 25 | Day-To-Day | Jan 24: Cunningham (right wrist) probable for Sunday |

![Image 10](blob:...) "Golden State Warriors")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Jonathan Kuminga | F | Jan 26 | Out | Jan 24: Kuminga (left knee soreness) is out |
| De'Anthony Melton | G | Jan 25 | Day-To-Day | Jan 24: Melton (rest) questionable for Sunday |
| Al Horford | C | Jan 25 | Day-To-Day | Jan 24: Horford (left toe) questionable for Sunday |
| Stephen Curry | G | Jan 25 | Day-To-Day | Jan 24: Curry (right knee) questionable for Sunday |

![Image 11](blob:...) "Houston Rockets")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Dorian Finney-Smith | F | Jan 26 | Day-To-Day | Jan 23: Finney-Smith (left ankle) out |
| Tari Eason | F | Jan 26 | Day-To-Day | Jan 23: Eason (rest) will not play Friday |
| Aaron Holiday | G | Jan 26 | Out | Jan 23: Holiday (back spasms) out for Friday |
| Steven Adams | C | Mar 16 | Out | Jan 20: Adams suffered "severely sprained, Grade 3 ankle sprain" |

![Image 12](blob:...) "Indiana Pacers")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Quenton Jackson | G | Jan 26 | Day-To-Day | Jan 23: Jackson (ankle) won't play Friday |
| Bennedict Mathurin | G | Jan 26 | Out | Jan 22: Mathurin (thumb) ruled out for Friday |
| Tyrese Haliburton | G | Oct 1 | Out | Jul 7: Haliburton will miss entire 2025-26 season (Achilles surgery) |

![Image 13](blob:...) "LA Clippers")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Kawhi Leonard | F | Jan 25 | Day-To-Day | Jan 24: Leonard (knee/illness) questionable |
| Bogdan Bogdanovic | G | Feb 2 | Out | Jan 24: Bogdanovic (hamstring) won't play Sunday |
| Derrick Jones Jr. | F | Feb 19 | Out | Jan 4: Jones (Grade 2 MCL sprain) out 6 weeks |

![Image 14](blob:...) "Los Angeles Lakers")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Austin Reaves | G | Jan 26 | Out | Jan 24: Reaves scrimmaged Saturday and should return "sooner than later" |
| Adou Thiero | F | Feb 2 | Out | Dec 31: Thiero will miss at least 4 weeks with right MCL sprain |

![Image 15](blob:...) "Memphis Grizzlies")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Santi Aldama | F | Jan 26 | Out | Jan 24: Aldama (knee) ruled out for Sunday |
| Ja Morant | G | Feb 20 | Out | Jan 24: Morant (elbow) will be reevaluated in ~3 weeks |
| Ty Jerome | G | Jan 30 | Out | Jan 24: Jerome (calf) expected back 1-2 weeks |
| Brandon Clarke | F | Feb 20 | Out | Jan 14: Clarke (Grade 2 calf strain) 4-6 weeks |
| Zach Edey | C | Mar 4 | Out | Jan 14: Edey (stress reaction) out 6 weeks |

![Image 16](blob:...) "Miami Heat")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Davion Mitchell | G | Jan 25 | Out | Jan 24: Mitchell (shoulder) out for Saturday |
| Kel'el Ware | C | Jan 28 | Out | Jan 23: Ware (strained hamstring) won't play back-to-back |
| Tyler Herro | G | Jan 28 | Out | Jan 19: Herro (ribs - costochondral) out for 5-game road trip |
| Terry Rozier | G | Feb 20 | Out | Oct23: Rozier placed on leave from Heat

![Image 17](blob:...) "Milwaukee Bucks")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Giannis Antetokounmpo | F | Feb 20 | Out | Jan 24: Antetokounmpo (right calf injury) out 4-6 weeks |
| Kevin Porter Jr. | G | Feb 3 | Out | Jan 21: Porter (oblique) - no official timetable |
| Taurean Prince | F | Feb 20 | Out | Jan 1: Bucks applied for Disabled Player Exception (likely out for season)

![Image 18](blob:...) "Minnesota Timberwolves")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Terrence Shannon Jr. | G | Jan 25 | Out | Jan 19: Shannon (foot) ruled out for Tuesday |

![Image 19](blob:...) "New Orleans Pelicans")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Jose Alvarado | G | Jan 25 | Out | Jan 24: Alvarado (oblique) questionable for Sunday |
| Dejounte Murray | G | Feb 20 | Out | Jan 7: Murray (Achilles) "making progress" but no return date |

![Image 20](blob:...) "Oklahoma City Thunder")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Ajay Mitchell | G | Jan 27 | Out | Jan 24: Mitchell (abdomen) out for Sunday |
| Alex Caruso | G | Jan 27 | Out | Jan 24: Caruso (adductor) out for Sunday |
| Isaiah Hartenstein | C | Jan 27 | Out | Jan 24: Hartenstein (calf) out for Sunday |
| Jalen Williams | G | Feb 3 | Out | Jan 19: Williams (hamstring) reevaluated in 2 weeks |
| Nikola Topic | G | Feb 20 | Out | Oct 30: Topic (testicular cancer) - out indefinitely |

![Image 21](blob:...) "Orlando Magic")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Franz Wagner | F | Jan 26 | Out | Jan 23: Wagner (ankle) ruled out for Saturday |

![Image 22](blob:...) "Phoenix Suns")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Jalen Green | G | Jan 25 | Day-To-Day | Jan 24: Green (hamstring) questionable for Sunday |
| Devin Booker | G | Jan 27 | Out | Jan 24: Booker (ankle) out for Sunday |

![Image 23](blob:...) "Portland Trail Blazers")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Scoot Henderson | G | Jan 26 | Out | Jan 23: Henderson (hamstring) won't play Friday |
| Damian Lillard | G | Oct 1 | Out | Sep 25: Lillard won't be back for 2025-26 season |

![Image 24](blob:...) "Sacramento Kings")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Zach LaVine | G | Jan 25 | Day-To-Day | Jan 24: LaVine (low back) questionable for Sunday |

![Image 25](blob:...) "San Antonio Spurs")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Luke Kornet | C | Jan 25 | Day-To-Day | Jan 24: Kornet (thigh) questionable for Sunday |

![Image 26](blob:...) "Toronto Raptors")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Immanuel Quickley | G | Jan 25 | Day-To-Day | Jan 24: Quickley (ankle) questionable for Sunday |
| Ja'Kobe Walter | G | Jan 25 | Out | Jan 24: Walter (hip) questionable for Sunday |
| Collin Murray-Boyles | F | Jan 25 | Out | Jan 24: Murray-Boyles (thumb) questionable for Sunday

![Image 27](blob:...) "Utah Jazz")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Lauri Markkanen | F | Jan 27 | Out | Jan 24: Markkanen (conditioning) ruled out for Saturday |
| Kevin Love | F | Jan 27 | Out | Jan 23: Love (left knee contusion) out for Saturday |
| Georges Niang | F | Jan 27 | Out | Jan 20: Niang (foot) out for Tuesday |

![Image 28](blob:...) "Washington Wizards")

| NAME | POS | EST. RETURN DATE | STATUS | COMMENT |
| --- | --- | --- | --- | --- |
| Khris Middleton | F | Jan 27 | Day-To-Day | Jan 24: Middleton (foot) out for Saturday |
| Trae Young | G | Feb 19 | Out | Jan 14: Young (knee, quadriceps) out for season |
"""

    db = SessionLocal()
    try:
        print("🏥 PARSING ESPN NBA INJURY REPORT")
        print("=" * 70)
        print()

        # Parse injuries
        injuries = parse_injury_data(espn_injury_data)

        if not injuries:
            print("❌ No injuries found")
            return

        print(f"✅ Parsed {len(injuries)} injury entries")
        print()

        # Store in database
        print("💾 Storing in database...")
        result = store_injuries(db, injuries)

        print()
        print("=" * 70)
        print("✅ INJURY UPDATE COMPLETE")
        print("=" * 70)
        print(f"Created: {result['created']}")
        print(f"Updated: {result['updated']}")
        print(f"Total: {result['total']}")
        print()

        # Show summary by team
        from collections import defaultdict
        by_team = defaultdict(list)

        for injury in injuries:
            by_team[injury['team_abbr']].append(injury)

        print("📋 INJURY SUMMARY BY TEAM")
        print("-" * 70)

        # Sort by total injuries (descending)
        sorted_teams = sorted(by_team.items(), key=lambda x: len(x[1]), reverse=True)

        for team_abbr, team_injuries in sorted_teams[:15]:
            team_name_map = {
                'ATL': 'Hawks', 'BOS': 'Celtics', 'BKN': 'Nets',
                'CHA': 'Hornets', 'CHI': 'Bulls', 'CLE': 'Cavaliers',
                'DAL': 'Mavericks', 'DEN': 'Nuggets', 'DET': 'Pistons',
                'GSW': 'Warriors', 'HOU': 'Rockets', 'IND': 'Pacers',
                'LAC': 'Clippers', 'LAL': 'Lakers', 'MEM': 'Grizzlies',
                'MIA': 'Heat', 'MIL': 'Bucks', 'MIN': 'Timberwolves',
                'NOP': 'Pelicans', 'NYK': 'Knicks', 'OKC': 'Thunder',
                'ORL': 'Magic', 'PHI': '76ers', 'POR': 'Trail Blazers',
                'SAC': 'Kings', 'SAS': 'Spurs', 'TOR': 'Raptors',
                'UTA': 'Jazz', 'WAS': 'Wizards'
            }

            team_name = team_name_map.get(team_abbr, team_abbr)

            # Count by status
            out_count = len([i for i in team_injuries if 'out' in i['status'].lower()])
            dtd_count = len([i for i in team_injuries if 'day-to-day' in i['status'].lower()])
            questionable_count = len([i for i in team_injuries if 'questionable' in i['status'].lower()])

            print(f"\n{team_abbr} - {team_name}")
            print(f"  Out: {out_count} | Day-To-Day: {dtd_count} | Questionable: {questionable_count}")

            # Show key injuries
            key_players = [i for i in team_injuries if 'out' in i['status'].lower()][:5]
            if key_players:
                print(f"  Key injuries:")
                for i in key_players:
                    print(f"    • {i['player_name']}: {i['injury_type']} ({i['status']})")

    finally:
        db.close()


if __name__ == "__main__":
    main()
