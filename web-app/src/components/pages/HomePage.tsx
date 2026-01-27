// ============================================================================
// HomePage.tsx - Dashboard with today's games and top predictions
// ============================================================================

import { useEffect, useRef } from 'react';
import { useGameStore, useLiveGames, useUpcomingGames, useGameCounts, useTodaySchedule } from '@/stores/useGameStore';
import { usePredictionStore, useTopPredictions, useTodayPredictions } from '@/stores/usePredictionStore';
import { useInjuryStore, useInjuryCounts, useOutPlayers } from '@/stores/useInjuryStore';
import { GameStatusBar } from '../layout/GameStatusBar';
import { Link } from '../Router';
import { formatGameDate } from '@/utils/formatters';
import type { TopPrediction } from '@/types/api.types';

export function HomePage() {
  const liveGames = useLiveGames();
  const upcomingGames = useUpcomingGames();
  const gameCounts = useGameCounts();
  const todaySchedule = useTodaySchedule();
  const topPredictions = useTopPredictions();
  const todayPredictions = useTodayPredictions();
  const injuryCounts = useInjuryCounts();
  const outPlayers = useOutPlayers();

  const { fetchTodaysGames, fetchSyncStatus } = useGameStore();
  const { fetchTopPredictions } = usePredictionStore();
  const { fetchInjuries } = useInjuryStore();

  const hasInitialized = useRef(false);

  useEffect(() => {
    if (!hasInitialized.current) {
      hasInitialized.current = true;
      fetchTodaysGames();
      fetchTopPredictions({ limit: 10, min_confidence: 0.7 });
      fetchInjuries();
      fetchSyncStatus();
    }
  }, []); // Empty deps - only run once

  return (
    <div className="home-page">
      <GameStatusBar />

      <main className="container">
        {/* Hero Section */}
        <section className="hero">
          <h1>NBA Sports Betting AI</h1>
          <p>AI-powered predictions, live odds, and sports betting insights</p>
        </section>

        {/* Stats Overview */}
        <section className="stats-overview">
          <StatCard
            label="Live Games"
            value={gameCounts.live}
            color="brand"
            icon="🔴"
          />
          <StatCard
            label="Today's Games"
            value={todaySchedule.count}
            color="blue"
            icon="📅"
          />
          <StatCard
            label="Top Predictions"
            value={topPredictions.length}
            color="green"
            icon="🎯"
          />
          <StatCard
            label="Injuries"
            value={injuryCounts.out}
            color="yellow"
            icon="🏥"
          />
        </section>

        {/* Live Games */}
        {liveGames.length > 0 && (
          <section className="section">
            <div className="section-header">
              <h2>🔴 Live Games</h2>
              <Link to="/predictions" className="view-all-link">View All</Link>
            </div>
            <div className="games-grid">
              {liveGames.map(game => (
                <GameCard key={game.id} game={game} />
              ))}
            </div>
          </section>
        )}

        {/* Upcoming Games */}
        {upcomingGames.length > 0 && (
          <section className="section">
            <div className="section-header">
              <h2>📅 Upcoming Games</h2>
              <Link to="/predictions" className="view-all-link">View All</Link>
            </div>
            <div className="games-grid">
              {upcomingGames.slice(0, 6).map(game => (
                <GameCard key={game.id} game={game} />
              ))}
            </div>
          </section>
        )}

        {/* Top Predictions */}
        {topPredictions.length > 0 && (
          <section className="section">
            <div className="section-header">
              <h2>🎯 Top Predictions</h2>
              <Link to="/predictions" className="view-all-link">View All</Link>
            </div>
            <div className="predictions-grid">
              {topPredictions.slice(0, 6).map((item: TopPrediction) => (
                <PredictionCard key={item.prediction.id} prediction={item.prediction} />
              ))}
            </div>
          </section>
        )}

        {/* Injury Report */}
        {outPlayers.length > 0 && (
          <section className="section">
            <div className="section-header">
              <h2>🏥 Injury Report</h2>
              <Link to="/injuries" className="view-all-link">View All</Link>
            </div>
            <div className="injury-list">
              {outPlayers.slice(0, 5).map(injury => (
                <InjuryCard key={injury.id} injury={injury} />
              ))}
            </div>
          </section>
        )}

        {/* Quick Links */}
        <section className="section quick-links">
          <h2>Explore</h2>
          <div className="quick-links-grid">
            <QuickLink
              to="/teams"
              title="All Teams"
              description="View all 30 NBA teams and rosters"
              icon="🏀"
            />
            <QuickLink
              to="/predictions"
              title="Predictions"
              description="AI-powered player prop predictions"
              icon="🎯"
            />
            <QuickLink
              to="/injuries"
              title="Injuries"
              description="Latest injury reports and updates"
              icon="🏥"
            />
            <QuickLink
              to="/parlays"
              title="Parlays"
              description="Top EV parlay combinations"
              icon="💰"
            />
          </div>
        </section>
      </main>
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: number;
  color: 'brand' | 'blue' | 'green' | 'yellow';
  icon: string;
}

function StatCard({ label, value, color, icon }: StatCardProps) {
  return (
    <div className={`stat-card stat-card-${color}`}>
      <span className="stat-icon">{icon}</span>
      <div className="stat-content">
        <span className="stat-value">{value}</span>
        <span className="stat-label">{label}</span>
      </div>
    </div>
  );
}

interface GameCardProps {
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

function GameCard({ game }: GameCardProps) {
  const isLive = game.status === 'in_progress';
  const isScheduled = game.status === 'scheduled';

  return (
    <Link to={`/game/${game.id}`} className="game-card">
      <div className="game-card-header">
        <span className={`game-status ${isLive ? 'live' : isScheduled ? 'scheduled' : ''}`}>
          {isLive && <span className="live-dot" />}
          {isLive && 'Live'}
          {isScheduled && formatGameDate(game.game_date)}
        </span>
      </div>
      <div className="game-card-body">
        <div className="team-row">
          <span className="team-abbr">{game.away_team}</span>
          {game.away_team_score !== null ? (
            <span className="team-score">{game.away_team_score}</span>
          ) : (
            <span className="vs">vs</span>
          )}
        </div>
        <div className="team-row">
          <span className="team-abbr">{game.home_team}</span>
          {game.home_team_score !== null ? (
            <span className="team-score">{game.home_team_score}</span>
          ) : (
            <span className="vs">@</span>
          )}
        </div>
      </div>
      {isLive && game.period && (
        <div className="game-card-footer">
          <span className="period-info">
            {game.period <= 4 ? `Q${game.period}` : `OT${game.period - 4}`}
            {game.time_remaining && ` • ${game.time_remaining}`}
          </span>
        </div>
      )}
    </Link>
  );
}

interface PredictionCardProps {
  prediction: {
    id: string;
    player_name: string;
    team: string;
    stat_type: string;
    predicted_value: number;
    bookmaker_line: number | null;
    recommendation: string;
    confidence: number;
    over_price: number | null;
    under_price: number | null;
  };
}

function PredictionCard({ prediction }: PredictionCardProps) {
  const confidencePercent = Math.round(prediction.confidence * 100);
  const line = prediction.bookmaker_line ?? prediction.predicted_value;

  return (
    <div className="prediction-card">
      <div className="prediction-header">
        <span className="player-name">{prediction.player_name}</span>
        <span className="team-abbr">{prediction.team}</span>
      </div>
      <div className="prediction-body">
        <div className="stat-type">{prediction.stat_type.toUpperCase()}</div>
        <div className="prediction-value">
          <span className="predicted">{prediction.predicted_value.toFixed(1)}</span>
          {prediction.bookmaker_line && (
            <>
              <span className="vs">vs</span>
              <span className="line">{line.toFixed(1)}</span>
            </>
          )}
        </div>
      </div>
      <div className="prediction-footer">
        <span className={`recommendation ${prediction.recommendation.toLowerCase()}`}>
          {prediction.recommendation}
        </span>
        <span className={`confidence ${confidencePercent >= 75 ? 'high' : confidencePercent >= 50 ? 'medium' : 'low'}`}>
          {confidencePercent}%
        </span>
      </div>
    </div>
  );
}

interface InjuryCardProps {
  injury: {
    id: string;
    player_name: string;
    team: string;
    status: string;
    injury_type: string;
    impact_description: string | null;
  };
}

function InjuryCard({ injury }: InjuryCardProps) {
  return (
    <div className="injury-card">
      <div className="injury-header">
        <span className="player-name">{injury.player_name}</span>
        <span className={`status-badge ${injury.status}`}>
          {injury.status.replace('-', ' ').toUpperCase()}
        </span>
      </div>
      <div className="injury-body">
        <span className="team-abbr">{injury.team}</span>
        <span className="injury-type">{injury.injury_type}</span>
      </div>
    </div>
  );
}

interface QuickLinkProps {
  to: string;
  title: string;
  description: string;
  icon: string;
}

function QuickLink({ to, title, description, icon }: QuickLinkProps) {
  return (
    <Link to={to} className="quick-link">
      <span className="quick-link-icon">{icon}</span>
      <div className="quick-link-content">
        <h3 className="quick-link-title">{title}</h3>
        <p className="quick-link-description">{description}</p>
      </div>
    </Link>
  );
}
