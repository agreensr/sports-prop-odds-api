// ============================================================================
// InjuriesPage.tsx - Injury tracker page
// ============================================================================

import { useEffect, useState } from 'react';
import { useInjuryStore, useInjuriesByStatus, useInjuryCounts } from '@/stores/useInjuryStore';
import { Link } from '../Router';
import './InjuriesPage.css';

export function InjuriesPage() {
  const { fetchInjuries, loading } = useInjuryStore();
  const injuriesByStatus = useInjuriesByStatus();
  const counts = useInjuryCounts();

  const [filter, setFilter] = useState<string>('all');

  useEffect(() => {
    fetchInjuries();
  }, [fetchInjuries]);

  const filteredInjuries = filter === 'all'
    ? Object.values(injuriesByStatus).flat()
    : injuriesByStatus[filter as keyof typeof injuriesByStatus] || [];

  return (
    <div className="injuries-page">
      <main className="container">
        <header className="page-header">
          <h1>Injury Report</h1>
          <p>Track all NBA player injuries and their impact</p>
        </header>

        {/* Stats Overview */}
        <section className="stats-bar">
          <StatBadge label="Out" value={counts.out} color="red" />
          <StatBadge label="Doubtful" value={counts.doubtful} color="orange" />
          <StatBadge label="Questionable" value={counts.questionable} color="yellow" />
          <StatBadge label="Day-to-Day" value={counts.dayToDay} color="blue" />
        </section>

        {/* Filter Tabs */}
        <section className="filter-tabs">
          <TabButton active={filter === 'all'} onClick={() => setFilter('all')}>
            All ({counts.total})
          </TabButton>
          <TabButton active={filter === 'out'} onClick={() => setFilter('out')}>
            Out ({counts.out})
          </TabButton>
          <TabButton active={filter === 'doubtful'} onClick={() => setFilter('doubtful')}>
            Doubtful ({counts.doubtful})
          </TabButton>
          <TabButton active={filter === 'questionable'} onClick={() => setFilter('questionable')}>
            Questionable ({counts.questionable})
          </TabButton>
          <TabButton active={filter === 'day-to-day'} onClick={() => setFilter('day-to-day')}>
            Day-to-Day ({counts.dayToDay})
          </TabButton>
        </section>

        {/* Injuries List */}
        {loading ? (
          <div className="loading">Loading injuries...</div>
        ) : filteredInjuries.length === 0 ? (
          <div className="empty-state">
            <p>No injuries found.</p>
            <Link to="/" className="btn btn-primary">Back to Home</Link>
          </div>
        ) : (
          <section className="injuries-grid">
            {filteredInjuries.map(injury => (
              <InjuryCard key={injury.id} injury={injury} />
            ))}
          </section>
        )}
      </main>
    </div>
  );
}

interface StatBadgeProps {
  label: string;
  value: number;
  color: 'red' | 'orange' | 'yellow' | 'blue';
}

function StatBadge({ label, value, color }: StatBadgeProps) {
  return (
    <div className={`stat-badge stat-badge-${color}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

function TabButton({ active, onClick, children }: TabButtonProps) {
  return (
    <button
      className={`tab ${active ? 'active' : ''}`}
      onClick={onClick}
    >
      {children}
    </button>
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
    updated_at: string;
  };
}

function InjuryCard({ injury }: InjuryCardProps) {
  return (
    <div className="injury-card-expanded">
      <div className="injury-header">
        <span className="player-name">{injury.player_name}</span>
        <span className={`status-badge ${injury.status}`}>
          {injury.status.replace('-', ' ').toUpperCase()}
        </span>
      </div>
      <div className="injury-body">
        <div className="injury-info">
          <span className="team-abbr">{injury.team}</span>
          <span className="injury-type">{injury.injury_type}</span>
        </div>
        {injury.impact_description && (
          <p className="impact-description">{injury.impact_description}</p>
        )}
      </div>
    </div>
  );
}
