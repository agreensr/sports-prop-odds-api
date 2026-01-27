// ============================================================================
// Injury Store - State management for injuries
// ============================================================================

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import React from 'react';
import type { InjuryState, Injury, InjuryFilters } from '@/types/api.types';
import { injuriesApi } from '@/services/api';
import { INJURY_STATUS_CONFIG } from '@/utils/constants';

interface InjuryActions extends InjuryState {
  // Actions
  fetchInjuries: (params?: { team?: string; status?: string }) => Promise<void>;
  setInjuries: (injuries: Injury[]) => void;
  setFilters: (filters: Partial<InjuryFilters>) => void;
  clearFilters: () => void;
  setError: (error: string | null) => void;
  reset: () => void;
  applyFilters: () => void;
}

const initialState: InjuryState = {
  injuries: [],
  filteredInjuries: [],
  filters: {},
  loading: false,
  error: null,
};

export const useInjuryStore = create<InjuryActions>()(
  persist(
    (set, get) => ({
      ...initialState,

      /**
       * Fetch injuries with optional filters
       */
      fetchInjuries: async (params) => {
        set({ loading: true, error: null });

        try {
          const injuries = await injuriesApi.getInjuries(params);
          set({ injuries, loading: false });
          get().applyFilters();
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to fetch injuries';
          set({ error: message, loading: false, injuries: [] });
        }
      },

      /**
       * Set injuries manually
       */
      setInjuries: (injuries) => {
        set({ injuries });
        get().applyFilters();
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
       * Apply current filters to injuries
       */
      applyFilters: () => {
        const { injuries, filters } = get();
        let filtered = [...injuries];

        // Filter by team
        if (filters.team) {
          filtered = filtered.filter(i => i.team === filters.team);
        }

        // Filter by status
        if (filters.status) {
          filtered = filtered.filter(i => i.status === filters.status);
        }

        // Sort by severity (priority) and then by date
        filtered.sort((a, b) => {
          const priorityA = INJURY_STATUS_CONFIG[a.status]?.priority || 0;
          const priorityB = INJURY_STATUS_CONFIG[b.status]?.priority || 0;
          if (priorityA !== priorityB) {
            return priorityB - priorityA; // Higher priority first
          }
          // Then by updated date (most recent first)
          return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        });

        set({ filteredInjuries: filtered });
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
      name: 'nba-injury-store',
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
 * Get injuries grouped by team
 */
export const useInjuriesByTeam = () => {
  const injuries = useInjuryStore((state) => state.filteredInjuries);

  return React.useMemo(() => {
    const grouped: Record<string, Injury[]> = {};

    injuries.forEach(injury => {
      if (!grouped[injury.team]) {
        grouped[injury.team] = [];
      }
      grouped[injury.team].push(injury);
    });

    return grouped;
  }, [injuries]);
};

/**
 * Get injuries grouped by status
 */
export const useInjuriesByStatus = () => {
  const injuries = useInjuryStore((state) => state.filteredInjuries);

  return React.useMemo(() => {
    const grouped: Record<string, Injury[]> = {
      out: [],
      doubtful: [],
      questionable: [],
      'day-to-day': [],
      available: [],
    };

    injuries.forEach(injury => {
      const status = injury.status;
      if (grouped[status]) {
        grouped[status].push(injury);
      }
    });

    return grouped;
  }, [injuries]);
};

/**
 * Get players that are out (highest priority)
 */
export const useOutPlayers = () => {
  const injuries = useInjuryStore((state) => state.filteredInjuries);
  return React.useMemo(() => injuries.filter(i => i.status === 'out'), [injuries]);
};

/**
 * Get players that are doubtful
 */
export const useDoubtfulPlayers = () => {
  const injuries = useInjuryStore((state) => state.filteredInjuries);
  return React.useMemo(() => injuries.filter(i => i.status === 'doubtful'), [injuries]);
};

/**
 * Get players that are questionable
 */
export const useQuestionablePlayers = () => {
  const injuries = useInjuryStore((state) => state.filteredInjuries);
  return React.useMemo(() => injuries.filter(i => i.status === 'questionable'), [injuries]);
};

/**
 * Get count of injuries by status
 */
export const useInjuryCounts = () => {
  const injuries = useInjuryStore((state) => state.filteredInjuries);

  return React.useMemo(
    () => ({
      out: injuries.filter(i => i.status === 'out').length,
      doubtful: injuries.filter(i => i.status === 'doubtful').length,
      questionable: injuries.filter(i => i.status === 'questionable').length,
      dayToDay: injuries.filter(i => i.status === 'day-to-day').length,
      available: injuries.filter(i => i.status === 'available').length,
      total: injuries.length,
    }),
    [injuries]
  );
};

/**
 * Get teams with injured players
 */
export const useTeamsWithInjuries = () => {
  const injuries = useInjuryStore((state) => state.filteredInjuries);

  return React.useMemo(() => {
    const teamCounts: Record<string, number> = {};

    injuries.forEach(injury => {
      teamCounts[injury.team] = (teamCounts[injury.team] || 0) + 1;
    });

    return teamCounts;
  }, [injuries]);
};

/**
 * Check if a specific player is injured
 */
export const usePlayerInjuryStatus = (playerName: string) => {
  const injuries = useInjuryStore((state) => state.injuries);

  return injuries.find(i =>
    i.player_name.toLowerCase() === playerName.toLowerCase()
  );
};
