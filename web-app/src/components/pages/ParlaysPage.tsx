// ============================================================================
// ParlaysPage.tsx - Top EV parlays page
// ============================================================================

import { useEffect, useState } from 'react';
import { parlaysApi } from '@/services/api';
import type { Parlay } from '@/types/api.types';
import { Link } from '../Router';
import { formatAmericanOdds, calculatePayout } from '@/utils/formatters';
import './ParlaysPage.css';

export function ParlaysPage() {
  const [parlays, setParlays] = useState<Parlay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadParlays();
  }, []);

  const loadParlays = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await parlaysApi.getTopEVParlays({ limit: 20, min_ev: 0.05 });
      setParlays(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load parlays');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="parlays-page">
      <main className="container">
        <header className="page-header">
          <h1>Top EV Parlays</h1>
          <p>High expected value parlay combinations</p>
        </header>

        {loading ? (
          <div className="loading">Loading parlays...</div>
        ) : error ? (
          <div className="error">
            <p>{error}</p>
            <button onClick={loadParlays} className="btn btn-primary">Retry</button>
          </div>
        ) : parlays.length === 0 ? (
          <div className="empty-state">
            <p>No parlays available at this time.</p>
            <Link to="/" className="btn btn-primary">Back to Home</Link>
          </div>
        ) : (
          <section className="parlays-list">
            {parlays.map(parlay => (
              <ParlayCard key={parlay.id} parlay={parlay} />
            ))}
          </section>
        )}
      </main>
    </div>
  );
}

interface ParlayCardProps {
  parlay: Parlay;
}

function ParlayCard({ parlay }: ParlayCardProps) {
  const evPercent = (parlay.expected_value * 100).toFixed(1);
  const probability = (parlay.combined_probability * 100).toFixed(1);
  const stake10Payout = calculatePayout(10, parlay.total_odds).toFixed(2);

  return (
    <div className="parlay-card">
      <div className="parlay-header">
        <div className="parlay-title">
          <span className="legs-count">{parlay.legs.length}-Leg Parlay</span>
          <span className="game-date">
            {parlay.game_date ? new Date(parlay.game_date).toLocaleDateString() : 'Multiple Dates'}
          </span>
        </div>
        <div className="parlay-odds">
          <span className="odds-value">{formatAmericanOdds(parlay.total_odds)}</span>
        </div>
      </div>

      <div className="parlay-body">
        <div className="legs-list">
          {parlay.legs.map((leg, index) => (
            <div key={index} className="leg-item">
              <span className="leg-number">{index + 1}</span>
              <div className="leg-info">
                <span className="player-name">{leg.player_name}</span>
                <span className="stat-line">
                  {leg.stat_type.toUpperCase()} {leg.selection} {leg.line}
                </span>
              </div>
              <span className="leg-odds">{formatAmericanOdds(leg.odds)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="parlay-footer">
        <div className="ev-indicator">
          <span className="ev-label">Expected Value</span>
          <span className={`ev-value ${parseFloat(evPercent) >= 10 ? 'high' : parseFloat(evPercent) >= 5 ? 'medium' : 'low'}`}>
            {evPercent}%
          </span>
        </div>
        <div className="probability-indicator">
          <span className="probability-label">Probability</span>
          <span className="probability-value">{probability}%</span>
        </div>
        <div className="payout-indicator">
          <span className="payout-label">$10 Pays</span>
          <span className="payout-value">${stake10Payout}</span>
        </div>
      </div>
    </div>
  );
}
