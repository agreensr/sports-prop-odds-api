// ============================================================================
// TeamDetailPage.tsx - Team roster and stats
// ============================================================================

import { useEffect } from 'react';
import { useTeamStore, useTeamByAbbr, useSortedRoster, useRosterByPosition } from '@/stores/useTeamStore';
import { usePredictionStore, usePredictionsByTeam } from '@/stores/usePredictionStore';
import { useInjuryStore, useInjuriesByTeam } from '@/stores/useInjuryStore';
import { Link, useNavigate } from '../Router';
import { formatPosition, formatHeight, formatWeight } from '@/utils/formatters';
import './TeamDetailPage.css';

interface TeamDetailPageProps {
  params: { param0: string };
}

export function TeamDetailPage({ params }: TeamDetailPageProps) {
  const teamAbbr = params.param0?.toUpperCase();
  const navigate = useNavigate();

  const team = useTeamByAbbr(teamAbbr || '');
  const roster = useSortedRoster();
  const { guards, forwards, centers, others } = useRosterByPosition();
  const { selectTeam, loading, error } = useTeamStore();

  const predictionsByTeam = usePredictionsByTeam();
  const teamPredictions = predictionsByTeam[teamAbbr || ''] || [];

  const injuriesByTeam = useInjuriesByTeam();
  const teamInjuries = injuriesByTeam[teamAbbr || ''] || [];

  useEffect(() => {
    if (teamAbbr) {
      selectTeam(team ?? null);
    } else {
      navigate('/teams');
    }
  }, [teamAbbr, team, selectTeam, navigate]);

  if (!team) {
    return (
      <div className="team-detail-page">
        <main className="container">
          <div className="loading">Loading team...</div>
        </main>
      </div>
    );
  }

  if (error) {
    return (
      <div className="team-detail-page">
        <main className="container">
          <div className="error">{error}</div>
          <Link to="/teams" className="back-link">← Back to Teams</Link>
        </main>
      </div>
    );
  }

  return (
    <div className="team-detail-page">
      <main className="container">
        {/* Header */}
        <header className="team-header">
          <Link to="/teams" className="back-link">← All Teams</Link>
          <div className="team-info">
            <h1>{team.nickname}</h1>
            <p>{team.city} • {team.conference} Conference, {team.division} Division</p>
          </div>
        </header>

        {loading ? (
          <div className="loading">Loading roster...</div>
        ) : (
          <>
            {/* Injuries */}
            {teamInjuries.length > 0 && (
              <section className="injuries-section">
                <h2>Injuries ({teamInjuries.length})</h2>
                <div className="injuries-list">
                  {teamInjuries.map(injury => (
                    <div key={injury.id} className="injury-item">
                      <span className="player-name">{injury.player_name}</span>
                      <span className={`status ${injury.status}`}>{injury.status.replace('-', ' ')}</span>
                      <span className="injury-type">{injury.injury_type}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Predictions */}
            {teamPredictions.length > 0 && (
              <section className="predictions-section">
                <h2>Predictions ({teamPredictions.length})</h2>
                <div className="predictions-preview">
                  {teamPredictions.slice(0, 3).map(pred => (
                    <div key={pred.id} className="prediction-item">
                      <span className="player-name">{pred.player_name}</span>
                      <span className="stat">{pred.stat_type.toUpperCase()}</span>
                      <span className={`rec ${pred.recommendation.toLowerCase()}`}>{pred.recommendation}</span>
                      <span className="confidence">{Math.round(pred.confidence * 100)}%</span>
                    </div>
                  ))}
                </div>
                <Link to="/predictions" className="view-all-link">View All Predictions</Link>
              </section>
            )}

            {/* Roster */}
            <section className="roster-section">
              <h2>Roster ({roster.length} players)</h2>

              {guards.length > 0 && (
                <div className="position-group">
                  <h3>Guards ({guards.length})</h3>
                  <PlayerTable players={guards} />
                </div>
              )}

              {forwards.length > 0 && (
                <div className="position-group">
                  <h3>Forwards ({forwards.length})</h3>
                  <PlayerTable players={forwards} />
                </div>
              )}

              {centers.length > 0 && (
                <div className="position-group">
                  <h3>Centers ({centers.length})</h3>
                  <PlayerTable players={centers} />
                </div>
              )}

              {others.length > 0 && (
                <div className="position-group">
                  <h3>Others ({others.length})</h3>
                  <PlayerTable players={others} />
                </div>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}

interface PlayerTableProps {
  players: Array<{
    player_id: number;
    first_name: string;
    last_name: string;
    full_name: string;
    jersey_number: number;
    position: string;
    height: string;
    weight: number;
  }>;
}

function PlayerTable({ players }: PlayerTableProps) {
  return (
    <div className="player-table">
      {players.map(player => (
        <div key={player.player_id} className="player-row">
          <span className="jersey-number">{player.jersey_number || '-'}</span>
          <span className="player-name">{player.full_name}</span>
          <span className="position">{formatPosition(player.position)}</span>
          <span className="height">{formatHeight(player.height)}</span>
          <span className="weight">{formatWeight(player.weight)}</span>
        </div>
      ))}
    </div>
  );
}
