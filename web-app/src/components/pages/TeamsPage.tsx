// ============================================================================
// TeamsPage.tsx - Team selector page
// ============================================================================

import { useEffect } from 'react';
import { useTeamStore, useTeamsByConference } from '@/stores/useTeamStore';
import { Link } from '../Router';
import { TEAM_COLORS } from '@/utils/constants';
import './TeamsPage.css';

export function TeamsPage() {
  const { teams, fetchTeams, loading, error } = useTeamStore();
  const { eastern, western } = useTeamsByConference();

  useEffect(() => {
    if (teams.length === 0) {
      fetchTeams();
    }
  }, [fetchTeams, teams.length]);

  return (
    <div className="teams-page">
      <main className="container">
        <header className="page-header">
          <h1>NBA Teams</h1>
          <p>Select a team to view roster, predictions, and injuries</p>
        </header>

        {loading ? (
          <div className="loading">Loading teams...</div>
        ) : error ? (
          <div className="error-state">
            <p className="error-message">{error}</p>
            <p className="error-hint">Unable to connect to the API. Please ensure the backend is running.</p>
          </div>
        ) : eastern.length === 0 && western.length === 0 ? (
          <div className="error-state">
            <p>No teams available. The API may be unavailable.</p>
          </div>
        ) : (
          <div className="teams-content">
            {/* Eastern Conference */}
            <section className="conference-section">
              <h2>Eastern Conference</h2>
              <div className="teams-grid">
                {eastern.map(team => (
                  <TeamLink key={team.id} team={team} />
                ))}
              </div>
            </section>

            {/* Western Conference */}
            <section className="conference-section">
              <h2>Western Conference</h2>
              <div className="teams-grid">
                {western.map(team => (
                  <TeamLink key={team.id} team={team} />
                ))}
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

interface TeamLinkProps {
  team: {
    id: string;
    abbreviation: string;
    full_name: string;
    nickname: string;
    city: string;
  };
}

function TeamLink({ team }: TeamLinkProps) {
  const colors = TEAM_COLORS[team.abbreviation] || { primary: '#374151', secondary: '#6b7280' };

  return (
    <Link to={`/team/${team.abbreviation}`} className="team-link">
      <div
        className="team-logo-placeholder"
        style={{ backgroundColor: colors.primary }}
      >
        {team.abbreviation}
      </div>
      <div className="team-info">
        <span className="team-name">{team.nickname}</span>
        <span className="team-city">{team.city}</span>
      </div>
    </Link>
  );
}
