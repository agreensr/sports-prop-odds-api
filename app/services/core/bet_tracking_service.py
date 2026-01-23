"""
Service for tracking placed bets and their results.
"""
import logging
from typing import List, Optional, Dict
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.nba.models import PlacedBet, PlacedBetLeg, Game, Prediction, Player

logger = logging.getLogger(__name__)


class BetTrackingService:
    """Service for managing placed bets on sportsbooks."""

    def __init__(self, db: Session):
        self.db = db

    def create_placed_bet(
        self,
        sportsbook: str,
        bet_id: str,
        bet_type: str,
        matchup: str,
        game_date: datetime,
        wager_amount: float,
        total_charged: float,
        odds: int,
        to_win: float,
        total_payout: float,
        placed_at: datetime,
        legs: List[Dict],
        game_id: Optional[str] = None
    ) -> str:
        """
        Create a new placed bet with legs.

        Args:
            sportsbook: Name of sportsbook ('FanDuel', 'DraftKings', etc.)
            bet_id: Sportsbook's bet ID
            bet_type: Type of bet ('same_game_parlay', 'multi_game_parlay', 'straight')
            matchup: Game matchup (e.g., 'IND @ BOS')
            game_date: Date/time of game
            wager_amount: Amount wagered
            total_charged: Total charged including fees
            odds: American odds (+760, +333, etc.)
            to_win: Potential profit
            total_payout: Total potential return
            placed_at: When bet was placed
            legs: List of leg dictionaries with player_name, player_team, stat_type, selection,
                  line, special_bet, and optionally predicted_value, model_confidence
            game_id: Optional game ID from our database

        Returns:
            ID of created bet
        """
        import uuid

        # Create placed bet
        bet = PlacedBet(
            id=str(uuid.uuid4()),
            sportsbook=sportsbook,
            bet_id=bet_id,
            bet_type=bet_type,
            game_id=game_id,
            matchup=matchup,
            game_date=game_date,
            wager_amount=wager_amount,
            total_charged=total_charged,
            odds=odds,
            to_win=to_win,
            total_payout=total_payout,
            placed_at=placed_at,
            created_at=datetime.utcnow()
        )

        self.db.add(bet)
        self.db.flush()  # Get the bet ID before creating legs

        # Create legs
        for leg_data in legs:
            leg = PlacedBetLeg(
                id=str(uuid.uuid4()),
                bet_id=bet.id,
                player_name=leg_data.get('player_name'),
                player_team=leg_data.get('player_team'),
                stat_type=leg_data.get('stat_type'),
                selection=leg_data.get('selection'),
                line=leg_data.get('line'),
                special_bet=leg_data.get('special_bet'),
                predicted_value=leg_data.get('predicted_value'),
                model_confidence=leg_data.get('model_confidence'),
                recommendation=leg_data.get('recommendation'),
                result='pending',
                created_at=datetime.utcnow()
            )
            self.db.add(leg)

        self.db.commit()
        logger.info(f"Created placed bet {bet.id} for {matchup} with {len(legs)} legs")
        return str(bet.id)

    def get_placed_bets(
        self,
        sportsbook: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """Get placed bets with optional filtering."""
        query = self.db.query(PlacedBet)

        if sportsbook:
            query = query.filter(PlacedBet.sportsbook == sportsbook)
        if status:
            query = query.filter(PlacedBet.status == status)

        query = query.order_by(PlacedBet.placed_at.desc())
        bets = query.limit(limit).all()

        results = []
        for bet in bets:
            bet_dict = self._bet_to_dict(bet, include_legs=True)
            results.append(bet_dict)

        return results

    def get_bet_details(self, bet_id: str) -> Optional[Dict]:
        """Get detailed information about a specific bet."""
        bet = self.db.query(PlacedBet).filter(PlacedBet.id == bet_id).first()

        if not bet:
            return None

        return self._bet_to_dict(bet, include_legs=True)

    def update_bet_result(
        self,
        bet_id: str,
        status: str,
        actual_payout: Optional[float] = None,
        leg_results: Optional[List[Dict]] = None
    ) -> bool:
        """
        Update bet results after game completion.

        Args:
            bet_id: Bet ID to update
            status: New status ('won', 'lost', 'push', 'cashed_out')
            actual_payout: Actual amount received
            leg_results: List of dicts with leg_id, result, actual_value

        Returns:
            True if updated successfully
        """
        bet = self.db.query(PlacedBet).filter(PlacedBet.id == bet_id).first()

        if not bet:
            logger.warning(f"Bet {bet_id} not found")
            return False

        bet.status = status
        bet.actual_payout = actual_payout
        bet.settled_at = datetime.utcnow()

        if actual_payout is not None:
            bet.profit_loss = actual_payout - bet.total_charged

        # Update leg results
        if leg_results:
            for leg_result in leg_results:
                leg = self.db.query(PlacedBetLeg).filter(
                    PlacedBetLeg.id == leg_result.get('leg_id')
                ).first()

                if leg:
                    leg.result = leg_result.get('result', 'pending')
                    leg.actual_value = leg_result.get('actual_value')

                    # Determine if bet was correct
                    if leg.result in ['won', 'lost']:
                        selection = leg.selection
                        actual = leg_result.get('actual_value')

                        if actual is not None and leg.line is not None:
                            if selection == 'OVER':
                                leg.was_correct = actual > leg.line
                            elif selection == 'UNDER':
                                leg.was_correct = actual < leg.line

        self.db.commit()
        logger.info(f"Updated bet {bet_id} status to {status}")
        return True

    def get_bet_summary(self) -> Dict:
        """Get summary statistics of placed bets."""
        total_bets = self.db.query(PlacedBet).count()
        pending_bets = self.db.query(PlacedBet).filter(PlacedBet.status == 'pending').count()
        won_bets = self.db.query(PlacedBet).filter(PlacedBet.status == 'won').count()
        lost_bets = self.db.query(PlacedBet).filter(PlacedBet.status == 'lost').count()

        # Calculate profit/loss
        from sqlalchemy import func, case

        profit_loss = self.db.query(
            func.sum(
                case(
                    (PlacedBet.profit_loss != None, PlacedBet.profit_loss),
                    else_=0
                )
            )
        ).scalar()

        total_wagered = self.db.query(func.sum(PlacedBet.total_charged)).scalar()

        win_rate = 0.0
        if won_bets + lost_bets > 0:
            win_rate = won_bets / (won_bets + lost_bets)

        return {
            'total_bets': total_bets,
            'pending_bets': pending_bets,
            'won_bets': won_bets,
            'lost_bets': lost_bets,
            'win_rate': round(win_rate * 100, 2),
            'total_wagered': round(total_wagered, 2) if total_wagered else 0,
            'profit_loss': round(profit_loss, 2) if profit_loss else 0
        }

    def _bet_to_dict(self, bet: PlacedBet, include_legs: bool = False) -> Dict:
        """Convert PlacedBet model to dictionary."""
        result = {
            'id': str(bet.id),
            'sportsbook': bet.sportsbook,
            'bet_id': bet.bet_id,
            'bet_type': bet.bet_type,
            'matchup': bet.matchup,
            'game_date': bet.game_date.isoformat(),
            'wager_amount': bet.wager_amount,
            'total_charged': bet.total_charged,
            'odds': bet.odds,
            'to_win': bet.to_win,
            'total_payout': bet.total_payout,
            'status': bet.status,
            'cash_out_value': bet.cash_out_value,
            'actual_payout': bet.actual_payout,
            'profit_loss': bet.profit_loss,
            'placed_at': bet.placed_at.isoformat(),
            'settled_at': bet.settled_at.isoformat() if bet.settled_at else None
        }

        if include_legs:
            result['legs'] = []
            for leg in sorted(bet.legs, key=lambda x: x.id):
                leg_dict = {
                    'id': str(leg.id),
                    'player_name': leg.player_name,
                    'player_team': leg.player_team,
                    'stat_type': leg.stat_type,
                    'selection': leg.selection,
                    'line': leg.line,
                    'special_bet': leg.special_bet,
                    'predicted_value': leg.predicted_value,
                    'model_confidence': leg.model_confidence,
                    'recommendation': leg.recommendation,
                    'result': leg.result,
                    'actual_value': leg.actual_value,
                    'was_correct': leg.was_correct
                }
                result['legs'].append(leg_dict)

        return result
