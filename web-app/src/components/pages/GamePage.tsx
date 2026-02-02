// ============================================================================
// GamePage.tsx - Individual game details
// ============================================================================

import { useEffect, useState } from 'react';
import { useGameStore, useGameById } from '@/stores/useGameStore';
import { Link } from '../Router';
import { formatGameDate, formatTimeRemaining } from '@/utils/formatters';
import './GamePage.css';

interface GamePageProps {
  params: { param0: string };
}

export function GamePage({ params }: GamePageProps) {
  const gameId = params.param0;
  const game = useGameById(gameId || '');
  const [predictions, setPredictions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = () => (path: string) => {
    window.location.hash = path;
  };

  useEffect(() => {
    if (!gameId) {
      navigate()('/');
      return;
    }

    loadGameData();
  }, [gameId]);

  const loadGameData = async () => {
    setLoading(true);
    try {
      // Fetch predictions for this game
      // In a real app, this would call the API
      setPredictions([]);
    } catch (err) {
      console.error('Failed to load game data:', err);
    } finally {
      setLoading(false);
    }
  };

  if (!game) {
    return (
      <div className="game-page">
        <main className="container">
          <div className="loading">Loading game...</div>
        </main>
      </div>
    );
  }

  const isLive = game.status === 'in_progress';
  const isScheduled = game.status === 'scheduled';
  const isFinal = game.status === 'final';

  return (
    <div className="game-page">
      <main className="container">
        <Link to="/" className="back-link">← Back to Home</Link>

        {/* Game Header */}
        <header className="game-header">
          <div className={`game-status-badge ${isLive ? 'live' : isScheduled ? 'scheduled' : isFinal ? 'final' : ''}`}>
            {isLive && <span className="live-dot" />}
            {isLive && 'LIVE'}
            {isScheduled && formatGameDate(game.game_date)}
            {isFinal && 'FINAL'}
          </div>

          <div className="game-teams">
            <div className="team away">
              <span className="team-abbr">{game.away_team}</span>
              {game.away_team_score !== null && (
                <span className="team-score">{game.away_team_score}</span>
              )}
            </div>
            <div className="vs">VS</div>
            <div className="team home">
              <span className="team-abbr">{game.home_team}</span>
              {game.home_team_score !== null && (
                <span className="team-score">{game.home_team_score}</span>
              )}
            </div>
          </div>

          {isLive && game.period && (
            <div className="game-time">
              {formatTimeRemaining(game.period, game.time_remaining)}
            </div>
          )}
        </header>

        {/* Predictions */}
        {loading ? (
          <div className="loading">Loading predictions...</div>
        ) : predictions.length > 0 ? (
          <section className="predictions-section">
            <h2>Predictions for This Game</h2>
            <div className="predictions-grid">
              {predictions.map((pred: any) => (
                <div key={pred.id} className="prediction-item">
                  <span className="player-name">{pred.player_name}</span>
                  <span className="stat">{pred.stat_type.toUpperCase()}</span>
                  <span className="prediction">{pred.predicted_value}</span>
                  <span className={`rec ${pred.recommendation.toLowerCase()}`}>{pred.recommendation}</span>
                </div>
              ))}
            </div>
          </section>
        ) : (
          <section className="empty-predictions">
            <p>No predictions available for this game yet.</p>
          </section>
        )}
      </main>
    </div>
  );
}
