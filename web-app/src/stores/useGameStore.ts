// ============================================================================
// Game Store - State management for games and live updates
// ============================================================================

import { create } from 'zustand';
import React from 'react';
import type { GameState, Game, SyncStatus } from '@/types/api.types';
import { gamesApi, syncApi } from '@/services/api';

interface GameActions extends GameState {
  // Actions
  fetchGames: (params?: { start_date?: string; end_date?: string; team?: string }) => Promise<void>;
  fetchTodaysGames: () => Promise<void>;
  setGames: (games: Game[]) => void;
  fetchSyncStatus: () => Promise<void>;
  setError: (error: string | null) => void;
  reset: () => void;
  categorizeGames: () => void;
}

const initialState: GameState = {
  games: [],
  liveGames: [],
  upcomingGames: [],
  completedGames: [],
  loading: false,
  error: null,
  syncStatus: null,
};

export const useGameStore = create<GameActions>((set, get) => ({
  ...initialState,

  /**
   * Fetch games with optional filters
   */
  fetchGames: async (params) => {
    set({ loading: true, error: null });

    try {
      const games = await gamesApi.getGames(params);
      set({ games, loading: false });
      get().categorizeGames();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch games';
      set({ error: message, loading: false, games: [] });
    }
  },

  /**
   * Fetch today's games
   */
  fetchTodaysGames: async () => {
    set({ loading: true, error: null });

    try {
      const games = await gamesApi.getTodaysGames();
      set({ games, loading: false });
      get().categorizeGames();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch today\'s games';
      set({ error: message, loading: false, games: [] });
    }
  },

  /**
   * Set games manually
   */
  setGames: (games) => {
    set({ games });
    get().categorizeGames();
  },

  /**
   * Fetch sync status
   */
  fetchSyncStatus: async () => {
    try {
      const syncStatus = await syncApi.getSyncStatus();
      set({ syncStatus });
    } catch (error) {
      // Don't set error for sync status failures - it's non-critical
      console.error('Failed to fetch sync status:', error);
    }
  },

  /**
   * Set error message
   */
  setError: (error) => {
    set({ error });
  },

  /**
   * Categorize games into live, upcoming, and completed
   */
  categorizeGames: () => {
    const { games } = get();
    const now = new Date();

    const live = games.filter(g => g.status === 'in_progress');
    const upcoming = games.filter(g => {
      const gameDate = new Date(g.game_date);
      return g.status === 'scheduled' && gameDate >= now;
    });
    const completed = games.filter(g => g.status === 'final' || g.status === 'cancelled');

    set({
      liveGames: live,
      upcomingGames: upcoming,
      completedGames: completed,
    });
  },

  /**
   * Reset store to initial state
   */
  reset: () => {
    set(initialState);
  },
}));

// ============================================================================
// Selectors
// ============================================================================

/**
 * Get all live games
 */
export const useLiveGames = () => {
  return useGameStore((state) => state.liveGames);
};

/**
 * Get all upcoming games
 */
export const useUpcomingGames = () => {
  return useGameStore((state) => state.upcomingGames);
};

/**
 * Get all completed games
 */
export const useCompletedGames = () => {
  return useGameStore((state) => state.completedGames);
};

/**
 * Check if there are any live games
 */
export const useHasLiveGames = () => {
  return useGameStore((state) => state.liveGames.length > 0);
};

/**
 * Get games for a specific team
 */
export const useTeamGames = (teamAbbr: string) => {
  const games = useGameStore((state) => state.games);
  return React.useMemo(
    () => games.filter(g => g.away_team === teamAbbr || g.home_team === teamAbbr),
    [games, teamAbbr]
  );
};

/**
 * Get a specific game by ID
 */
export const useGameById = (gameId: string) => {
  return useGameStore((state) =>
    state.games.find(g => g.id === gameId)
  );
};

/**
 * Get games grouped by date
 */
export const useGamesByDate = () => {
  const games = useGameStore((state) => state.games);

  return React.useMemo(() => {
    const grouped: Record<string, Game[]> = {};

    games.forEach(game => {
      const date = game.game_date.split('T')[0];
      if (!grouped[date]) {
        grouped[date] = [];
      }
      grouped[date].push(game);
    });

    // Sort dates (most recent first)
    const sortedDates = Object.keys(grouped).sort((a, b) => new Date(b).getTime() - new Date(a).getTime());

    return sortedDates.map(date => ({
      date,
      games: grouped[date],
    }));
  }, [games]);
};

/**
 * Get sync status with helper properties
 */
export const useSyncStatus = () => {
  const syncStatus = useGameStore((state) => state.syncStatus);

  return React.useMemo(
    () => ({
      isSyncing: syncStatus?.is_syncing ?? false,
      lastSync: syncStatus?.last_sync ?? null,
      nextSync: syncStatus?.next_sync ?? null,
      syncType: syncStatus?.sync_type ?? null,
      details: syncStatus?.details ?? null,
      raw: syncStatus,
    }),
    [syncStatus]
  );
};

/**
 * Get game counts by status
 */
export const useGameCounts = () => {
  const games = useGameStore((state) => state.games);

  return React.useMemo(
    () => ({
      total: games.length,
      live: games.filter(g => g.status === 'in_progress').length,
      scheduled: games.filter(g => g.status === 'scheduled').length,
      final: games.filter(g => g.status === 'final').length,
      cancelled: games.filter(g => g.status === 'cancelled').length,
    }),
    [games]
  );
};

/**
 * Get today's game schedule
 */
export const useTodaySchedule = () => {
  const games = useGameStore((state) => state.games);

  return React.useMemo(() => {
    const today = new Date().toISOString().split('T')[0];
    const todayGames = games.filter(g => g.game_date.startsWith(today));
    return {
      games: todayGames,
      count: todayGames.length,
    };
  }, [games]);
};

/**
 * Get games that need polling (for smart polling)
 */
export const useGamesNeedingPolling = () => {
  const games = useGameStore((state) => state.games);

  return React.useMemo(() => {
    const now = new Date();

    // Filter games that need polling
    return games.filter(game => {
      const gameDate = new Date(game.game_date);
      const minutesToGame = (gameDate.getTime() - now.getTime()) / 60000;

      // Live games
      if (game.status === 'in_progress') {
        return true;
      }

      // Games starting within 30 minutes
      if (game.status === 'scheduled' && minutesToGame > 0 && minutesToGame <= 30) {
        return true;
      }

      return false;
    });
  }, [games]);
};
