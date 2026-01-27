// ============================================================================
// GameStatusBar.tsx - Live game ticker with smart polling
// ============================================================================

import { useEffect, useCallback, useRef } from 'react';
import { useGameStore, useLiveGames, useUpcomingGames } from '@/stores/useGameStore';
import { useGameStatusPolling } from '@/hooks/useSmartPolling';
import { formatGameDate } from '@/utils/formatters';
import { Link } from '../Router';
import './GameStatusBar.css';

export function GameStatusBar() {
  const liveGames = useLiveGames();
  const upcomingGames = useUpcomingGames();
  const { fetchTodaysGames, fetchSyncStatus } = useGameStore();
  const hasInitialized = useRef(false);

  // Fetch games on mount (only once)
  useEffect(() => {
    if (!hasInitialized.current) {
      hasInitialized.current = true;
      fetchTodaysGames();
      fetchSyncStatus();
    }
  }, []); // Empty deps - only run once on mount

  // Smart polling for live games - use stable callback
  const handlePoll = useCallback(async () => {
    fetchTodaysGames();
    fetchSyncStatus();
  }, []); // Empty deps - functions are stable from Zustand

  useGameStatusPolling(
    [...liveGames, ...upcomingGames.slice(0, 5)], // Poll live and next 5 upcoming
    handlePoll,
    {
      enabled: liveGames.length > 0 || upcomingGames.length > 0,
      pauseWhenHidden: true,
    }
  );

  // Combine games for ticker
  const tickerGames = [...liveGames, ...upcomingGames].slice(0, 10);

  if (tickerGames.length === 0) {
    return (
      <div className="game-status-bar empty">
        <div className="container">
          <p className="no-games-message">No games scheduled today</p>
        </div>
      </div>
    );
  }

  return (
    <div className="game-status-bar">
      <div className="game-status-container">
        <div className="game-status-label">
          <span className="live-indicator" />
          <span>Live Scores</span>
        </div>
        <div className="game-ticker">
          {tickerGames.map((game) => (
            <GameTickerItem key={game.id} game={game} />
          ))}
        </div>
      </div>
    </div>
  );
}

interface GameTickerItemProps {
  game: {
    id: string;
    away_team: string;
    home_team: string;
    away_team_score: number | null;
    home_team_score: number | null;
    status: string;
    game_date: string;
    period: number | null;
    time_remaining: string | null;
  };
}

function GameTickerItem({ game }: GameTickerItemProps) {
  const isLive = game.status === 'in_progress';
  const isScheduled = game.status === 'scheduled';
  const isFinal = game.status === 'final';

  return (
    <Link to={`/game/${game.id}`} className="game-ticker-item">
      {/* Status Badge */}
      <span className={`game-status-badge ${isLive ? 'live' : isScheduled ? 'scheduled' : isFinal ? 'final' : ''}`}>
        {isLive && <span className="live-dot" />}
        {isLive && game.period && (
          <span className="period-indicator">
            {game.period <= 4 ? `Q${game.period}` : `OT${game.period - 4}`}
          </span>
        )}
        {isScheduled && formatGameDate(game.game_date)}
        {isFinal && 'Final'}
      </span>

      {/* Teams & Score */}
      <span className="game-teams">
        <span className="team-abbr">{game.away_team}</span>
        {game.away_team_score !== null && (
          <span className={`team-score ${game.away_team_score > game.home_team_score! ? 'winning' : ''}`}>
            {game.away_team_score}
          </span>
        )}
        {game.away_team_score === null && <span className="vs">vs</span>}

        <span className="team-abbr">{game.home_team}</span>
        {game.home_team_score !== null && (
          <span className={`team-score ${game.home_team_score > game.away_team_score! ? 'winning' : ''}`}>
            {game.home_team_score}
          </span>
        )}
        {game.home_team_score === null && <span className="vs">@</span>}
      </span>

      {/* Time Remaining (for live games) */}
      {isLive && game.time_remaining && (
        <span className="time-remaining">{game.time_remaining}</span>
      )}
    </Link>
  );
}
