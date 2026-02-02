// ============================================================================
// Team Store - State management for teams and rosters
// ============================================================================

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import React from 'react';
import type { TeamState, NBATeam, NBAPlayer } from '@/types/api.types';
import { teamsApi } from '@/services/api';
import { TEAM_NAME_MAP } from '@/utils/constants';

interface TeamActions extends TeamState {
  // Actions
  fetchTeams: () => Promise<void>;
  selectTeam: (team: NBATeam | null) => void;
  fetchRoster: (teamAbbr: string) => Promise<void>;
  clearRoster: () => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState: TeamState = {
  teams: [],
  selectedTeam: null,
  roster: [],
  loading: false,
  error: null,
};

export const useTeamStore = create<TeamActions>()(
  persist(
    (set, get) => ({
      ...initialState,

      /**
       * Fetch all NBA teams
       */
      fetchTeams: async () => {
        set({ loading: true, error: null });

        try {
          const teams = await teamsApi.getTeams();
          // Ensure teams is always an array
          set({ teams: Array.isArray(teams) ? teams : [], loading: false });
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to fetch teams';
          set({ teams: [], error: message, loading: false });
        }
      },

      /**
       * Select a team
       */
      selectTeam: (team) => {
        set({ selectedTeam: team });

        // Auto-fetch roster when a team is selected
        if (team) {
          get().fetchRoster(team.abbreviation);
        } else {
          get().clearRoster();
        }
      },

      /**
       * Fetch roster for a team
       */
      fetchRoster: async (teamAbbr: string) => {
        set({ loading: true, error: null });

        try {
          // Use the team's full name for the search
          const teamName = TEAM_NAME_MAP[teamAbbr] || teamAbbr;
          const roster = await teamsApi.getTeamPlayers(teamName);
          set({ roster, loading: false });
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to fetch roster';
          set({ error: message, loading: false, roster: [] });
        }
      },

      /**
       * Clear the current roster
       */
      clearRoster: () => {
        set({ roster: [] });
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
      name: 'nba-team-store',
      partialize: (state) => ({
        selectedTeam: state.selectedTeam,
      }),
    }
  )
);

// ============================================================================
// Selectors
// ============================================================================

/**
 * Get all teams sorted by conference and division
 */
export const useSortedTeams = () => {
  const teams = useTeamStore((state) => state.teams);

  return React.useMemo(
    () =>
      [...teams].sort((a, b) => {
        // First sort by conference
        if (a.conference !== b.conference) {
          return a.conference === 'East' ? -1 : 1;
        }
        // Then by division
        if (a.division !== b.division) {
          return a.division.localeCompare(b.division);
        }
        // Finally by name
        return a.nickname.localeCompare(b.nickname);
      }),
    [teams]
  );
};

/**
 * Get teams grouped by conference
 */
export const useTeamsByConference = () => {
  const teams = useTeamStore((state) => state.teams);

  return React.useMemo(
    () => ({
      eastern: Array.isArray(teams) ? teams.filter(t => t.conference === 'East') : [],
      western: Array.isArray(teams) ? teams.filter(t => t.conference === 'West') : [],
    }),
    [teams]
  );
};

/**
 * Get teams grouped by division
 */
export const useTeamsByDivision = () => {
  const teams = useTeamStore((state) => state.teams);

  return React.useMemo(() => {
    const divisions: Record<string, NBATeam[]> = {};

    teams.forEach(team => {
      const key = `${team.conference}-${team.division}`;
      if (!divisions[key]) {
        divisions[key] = [];
      }
      divisions[key].push(team);
    });

    return divisions;
  }, [teams]);
};

/**
 * Get a team by abbreviation
 */
export const useTeamByAbbr = (abbr: string) => {
  return useTeamStore((state) =>
    state.teams.find(t => t.abbreviation === abbr)
  );
};

/**
 * Get roster sorted by jersey number
 */
export const useSortedRoster = () => {
  const roster = useTeamStore((state) => state.roster);

  return React.useMemo(
    () =>
      [...roster].sort((a, b) => {
        // Sort by jersey number, putting players without numbers at the end
        if (!a.jersey_number) return 1;
        if (!b.jersey_number) return -1;
        return a.jersey_number - b.jersey_number;
      }),
    [roster]
  );
};

/**
 * Get roster grouped by position
 */
export const useRosterByPosition = () => {
  const roster = useTeamStore((state) => state.roster);

  return React.useMemo(
    () => {
      const guards = roster.filter(p => p.position === 'PG' || p.position === 'SG' || p.position === 'G');
      const forwards = roster.filter(p => p.position === 'SF' || p.position === 'PF' || p.position === 'F');
      const centers = roster.filter(p => p.position === 'C');
      const others = roster.filter(p => !['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F'].includes(p.position));

      return {
        guards,
        forwards,
        centers,
        others,
        all: roster,
      };
    },
    [roster]
  );
};
