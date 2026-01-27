// ============================================================================
// Prediction Store - State management for predictions
// ============================================================================

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import React from 'react';
import type { PredictionState, Prediction, TopPrediction, PredictionFilters } from '@/types/api.types';
import { predictionsApi } from '@/services/api';

interface PredictionActions extends PredictionState {
  // Actions
  fetchPredictions: (params?: { game_date?: string; team?: string }) => Promise<void>;
  fetchTopPredictions: (params?: { limit?: number; min_confidence?: number }) => Promise<void>;
  setPredictions: (predictions: Prediction[]) => void;
  setTopPredictions: (predictions: TopPrediction[]) => void;
  setFilters: (filters: Partial<PredictionFilters>) => void;
  clearFilters: () => void;
  setError: (error: string | null) => void;
  reset: () => void;
  applyFilters: () => void;
}

const initialState: PredictionState = {
  predictions: [],
  topPredictions: [],
  filteredPredictions: [],
  filters: {},
  loading: false,
  error: null,
};

export const usePredictionStore = create<PredictionActions>()(
  persist(
    (set, get) => ({
      ...initialState,

      /**
       * Fetch predictions with optional filters
       */
      fetchPredictions: async (params) => {
        set({ loading: true, error: null });

        try {
          const predictions = await predictionsApi.getPredictionsWithOdds(params);
          set({ predictions, loading: false });
          get().applyFilters();
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to fetch predictions';
          set({ error: message, loading: false, predictions: [] });
        }
      },

      /**
       * Fetch top predictions
       */
      fetchTopPredictions: async (params) => {
        set({ loading: true, error: null });

        try {
          const topPredictions = await predictionsApi.getTopPredictions(params);
          set({ topPredictions, loading: false });
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to fetch top predictions';
          set({ error: message, loading: false, topPredictions: [] });
        }
      },

      /**
       * Set predictions manually
       */
      setPredictions: (predictions) => {
        set({ predictions });
        get().applyFilters();
      },

      /**
       * Set top predictions manually
       */
      setTopPredictions: (topPredictions) => {
        set({ topPredictions });
      },

      /**
       * Update filters and apply them
       */
      setFilters: (newFilters) => {
        set((state) => ({
          filters: { ...state.filters, ...newFilters },
        }));
        get().applyFilters();
      },

      /**
       * Clear all filters
       */
      clearFilters: () => {
        set({ filters: {} });
        get().applyFilters();
      },

      /**
       * Apply current filters to predictions
       */
      applyFilters: () => {
        const { predictions, filters } = get();
        let filtered = [...predictions];

        // Filter by team
        if (filters.team) {
          filtered = filtered.filter(p => p.team === filters.team);
        }

        // Filter by stat type
        if (filters.statType) {
          filtered = filtered.filter(p => p.stat_type === filters.statType);
        }

        // Filter by minimum confidence
        if (filters.minConfidence !== undefined) {
          filtered = filtered.filter(p => p.confidence >= filters.minConfidence!);
        }

        // Filter by recommendation
        if (filters.recommendation) {
          filtered = filtered.filter(p => p.recommendation === filters.recommendation);
        }

        // Filter by date range
        if (filters.dateFrom) {
          filtered = filtered.filter(p => p.game_date >= filters.dateFrom!);
        }
        if (filters.dateTo) {
          filtered = filtered.filter(p => p.game_date <= filters.dateTo!);
        }

        // Sort by confidence (descending)
        filtered.sort((a, b) => b.confidence - a.confidence);

        set({ filteredPredictions: filtered });
      },

      /**
       * Set error message
       */
      setError: (error) => {
        set({ error });
      },

      /**
       * Reset store to initial state
       */
      reset: () => {
        set(initialState);
      },
    }),
    {
      name: 'nba-prediction-store',
      partialize: (state) => ({
        filters: state.filters,
      }),
    }
  )
);

// ============================================================================
// Selectors
// ============================================================================

/**
 * Get top predictions from the store
 */
export const useTopPredictions = () => {
  return usePredictionStore((state) => state.topPredictions);
};

/**
 * Get predictions grouped by team
 */
export const usePredictionsByTeam = () => {
  const predictions = usePredictionStore((state) => state.filteredPredictions);

  // Use useMemo to cache the grouped result
  return React.useMemo(() => {
    const grouped: Record<string, Prediction[]> = {};

    predictions.forEach(prediction => {
      if (!grouped[prediction.team]) {
        grouped[prediction.team] = [];
      }
      grouped[prediction.team].push(prediction);
    });

    return grouped;
  }, [predictions]);
};

/**
 * Get predictions grouped by stat type
 */
export const usePredictionsByStatType = () => {
  const predictions = usePredictionStore((state) => state.filteredPredictions);

  // Use useMemo to cache the grouped result
  return React.useMemo(() => {
    const grouped: Record<string, Prediction[]> = {
      points: [],
      rebounds: [],
      assists: [],
      threes: [],
      pra: [],
      pr: [],
      pa: [],
    };

    predictions.forEach(prediction => {
      const statType = prediction.stat_type;
      if (grouped[statType]) {
        grouped[statType].push(prediction);
      }
    });

    return grouped;
  }, [predictions]);
};

/**
 * Get high confidence predictions (75%+)
 */
export const useHighConfidencePredictions = () => {
  return usePredictionStore((state) =>
    state.filteredPredictions.filter(p => p.confidence >= 0.75)
  );
};

/**
 * Get predictions with over recommendation
 */
export const useOverPredictions = () => {
  return usePredictionStore((state) =>
    state.filteredPredictions.filter(p => p.recommendation === 'OVER')
  );
};

/**
 * Get predictions with under recommendation
 */
export const useUnderPredictions = () => {
  return usePredictionStore((state) =>
    state.filteredPredictions.filter(p => p.recommendation === 'UNDER')
  );
};

/**
 * Get today's predictions
 */
export const useTodayPredictions = () => {
  const today = new Date().toISOString().split('T')[0];
  const predictions = usePredictionStore((state) => state.filteredPredictions);
  return predictions.filter(p => p.game_date.startsWith(today));
};

/**
 * Get upcoming predictions (future games)
 */
export const useUpcomingPredictions = () => {
  const now = new Date().toISOString();
  const predictions = usePredictionStore((state) => state.filteredPredictions);
  return predictions.filter(p => p.game_date > now);
};

/**
 * Get count of active filters
 */
export const useActiveFilterCount = () => {
  const filters = usePredictionStore((state) => state.filters);
  return Object.values(filters).filter(v => v !== undefined && v !== '').length;
};

/**
 * Check if any filter is active
 */
export const useHasActiveFilters = () => {
  return useActiveFilterCount() > 0;
};
