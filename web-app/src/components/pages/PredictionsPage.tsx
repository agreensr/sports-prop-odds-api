// ============================================================================
// PredictionsPage.tsx - All predictions with filters
// ============================================================================

import { useEffect, useState } from 'react';
import { usePredictionStore, useTodayPredictions } from '@/stores/usePredictionStore';
import { formatAmericanOdds, formatConfidence } from '@/utils/formatters';
import { Link } from '../Router';
import './PredictionsPage.css';

export function PredictionsPage() {
  const todayPredictions = useTodayPredictions();
  const { fetchPredictions, filters, setFilters, clearFilters, loading } = usePredictionStore();

  const [localFilters, setLocalFilters] = useState({
    statType: '',
    minConfidence: '',
    recommendation: '',
  });

  useEffect(() => {
    fetchPredictions();
  }, [fetchPredictions]);

  const handleFilterChange = (key: string, value: string) => {
    setLocalFilters(prev => ({ ...prev, [key]: value }));
  };

  const applyFilters = () => {
    const newFilters: Record<string, string | number> = {};
    if (localFilters.statType) newFilters.statType = localFilters.statType;
    if (localFilters.minConfidence) newFilters.minConfidence = parseFloat(localFilters.minConfidence) / 100;
    if (localFilters.recommendation) newFilters.recommendation = localFilters.recommendation.toUpperCase();
    setFilters(newFilters);
  };

  const clearAllFilters = () => {
    setLocalFilters({ statType: '', minConfidence: '', recommendation: '' });
    clearFilters();
  };

  return (
    <div className="predictions-page">
      <main className="container">
        <header className="page-header">
          <h1>Predictions</h1>
          <p>AI-powered player prop predictions with live odds</p>
        </header>

        {/* Filters */}
        <section className="filters-section">
          <div className="filter-group">
            <select
              value={localFilters.statType}
              onChange={(e) => handleFilterChange('statType', e.target.value)}
            >
              <option value="">All Stats</option>
              <option value="points">Points</option>
              <option value="rebounds">Rebounds</option>
              <option value="assists">Assists</option>
              <option value="threes">Threes</option>
            </select>

            <select
              value={localFilters.minConfidence}
              onChange={(e) => handleFilterChange('minConfidence', e.target.value)}
            >
              <option value="">All Confidence</option>
              <option value="75">75%+</option>
              <option value="50">50%+</option>
              <option value="25">25%+</option>
            </select>

            <select
              value={localFilters.recommendation}
              onChange={(e) => handleFilterChange('recommendation', e.target.value)}
            >
              <option value="">All Picks</option>
              <option value="over">Over</option>
              <option value="under">Under</option>
            </select>
          </div>

          <div className="filter-actions">
            <button onClick={applyFilters} className="btn btn-primary">Apply Filters</button>
            <button onClick={clearAllFilters} className="btn btn-secondary">Clear</button>
          </div>
        </section>

        {/* Predictions */}
        {loading ? (
          <div className="loading">Loading predictions...</div>
        ) : todayPredictions.length === 0 ? (
          <div className="empty-state">
            <p>No predictions available for today.</p>
            <Link to="/" className="btn btn-primary">Back to Home</Link>
          </div>
        ) : (
          <section className="predictions-list">
            {todayPredictions.map(prediction => (
              <PredictionCard key={prediction.id} prediction={prediction} />
            ))}
          </section>
        )}
      </main>
    </div>
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
    game_date: string;
  };
}

function PredictionCard({ prediction }: PredictionCardProps) {
  const confidencePercent = Math.round(prediction.confidence * 100);
  const line = prediction.bookmaker_line ?? prediction.predicted_value;
  const edge = prediction.bookmaker_line
    ? ((prediction.predicted_value - prediction.bookmaker_line) / prediction.bookmaker_line * 100)
    : 0;

  return (
    <div className="prediction-card-expanded">
      <div className="prediction-header">
        <div className="player-info">
          <span className="player-name">{prediction.player_name}</span>
          <span className="team-abbr">{prediction.team}</span>
        </div>
        <div className="confidence-badge">
          <span className={`confidence-value ${confidencePercent >= 75 ? 'high' : confidencePercent >= 50 ? 'medium' : 'low'}`}>
            {confidencePercent}%
          </span>
        </div>
      </div>

      <div className="prediction-body">
        <div className="stat-info">
          <span className="stat-type">{prediction.stat_type.toUpperCase()}</span>
          <div className="line-comparison">
            <span className="predicted">{prediction.predicted_value.toFixed(1)}</span>
            <span className="vs">vs</span>
            <span className="line">{line.toFixed(1)}</span>
          </div>
        </div>

        {edge !== 0 && (
          <div className="edge-indicator">
            <span className={`edge-value ${edge >= 0 ? 'positive' : 'negative'}`}>
              {edge >= 0 ? '+' : ''}{edge.toFixed(1)}% edge
            </span>
          </div>
        )}
      </div>

      <div className="prediction-footer">
        <div className="recommendation-section">
          <span className={`recommendation ${prediction.recommendation.toLowerCase()}`}>
            {prediction.recommendation}
          </span>
          <span className="at-line">@ {line.toFixed(1)}</span>
        </div>

        <div className="odds-section">
          {prediction.over_price !== null && (
            <span className="odds">
              O: {formatAmericanOdds(prediction.over_price)}
            </span>
          )}
          {prediction.under_price !== null && (
            <span className="odds">
              U: {formatAmericanOdds(prediction.under_price)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
