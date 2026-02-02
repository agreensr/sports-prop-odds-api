// ============================================================================
// useGameSchedule Hook - Game time calculations for smart polling
// ============================================================================

import { useMemo } from 'react';
import { parseISO, differenceInMinutes, isAfter, isBefore, addMinutes } from 'date-fns';
import type { Game, GameTimeStatus } from '@/types/api.types';
import { GAME_TIME_THRESHOLDS } from '@/utils/constants';

/**
 * Calculate game time status for smart polling
 *
 * This hook determines:
 * - Whether to poll predictions (30 min before game)
 * - Whether to poll injuries (60 min before game)
 * - Whether to poll game status (during live games)
 * - The appropriate polling interval (3min normal, 30sec end game)
 */
export const useGameSchedule = (game: Game | null) => {
  const gameTimeStatus = useMemo((): GameTimeStatus => {
    // Default values when no game is provided
    const defaultStatus: GameTimeStatus = {
      shouldPollPredictions: false,
      shouldPollInjuries: false,
      shouldPollGameStatus: false,
      gameStatusInterval: 3 * 60 * 1000, // 3 minutes
      minutesToGame: 0,
      isLastTwoMinutes: false,
      isGameToday: false,
    };

    if (!game || !game.game_date) {
      return defaultStatus;
    }

    const now = new Date();
    const gameStart = parseISO(game.game_date);
    const minutesToGame = differenceInMinutes(gameStart, now);
    const isGameToday = gameStart.toDateString() === now.toDateString();

    // Determine if we should poll predictions
    // Poll predictions starting 30 minutes before game
    const shouldPollPredictions =
      minutesToGame <= GAME_TIME_THRESHOLDS.PREDICTIONS_FETCH &&
      minutesToGame > 0 &&
      game.status === 'scheduled';

    // Determine if we should poll injuries
    // Poll injuries starting 60 minutes before game
    const shouldPollInjuries =
      minutesToGame <= GAME_TIME_THRESHOLDS.INJURIES_START &&
      game.status !== 'final' &&
      game.status !== 'cancelled';

    // Determine if we should poll game status
    // Only poll live games
    const shouldPollGameStatus = game.status === 'in_progress';

    // Determine polling interval for game status
    // Default to 3 minutes
    let gameStatusInterval = 3 * 60 * 1000;

    // Check if we're in the last 2 minutes of a game
    let isLastTwoMinutes = false;

    if (game.status === 'in_progress') {
      // For in-progress games, we'd need game time data
      // Since the API doesn't provide exact game time, we'll use
      // a heuristic based on status and period
      const gameDuration = minutesToGame + (game.period || 0) * 12; // Approximate
      isLastTwoMinutes = game.period === 4 && game.time_remaining !== null && (
        parseInt(game.time_remaining, 10) <= 2 ||
        game.time_remaining.includes('0:') ||
        game.time_remaining.includes('1:')
      );

      if (isLastTwoMinutes) {
        gameStatusInterval = 30 * 1000; // 30 seconds
      }
    }

    return {
      shouldPollPredictions,
      shouldPollInjuries,
      shouldPollGameStatus,
      gameStatusInterval,
      minutesToGame,
      isLastTwoMinutes,
      isGameToday,
    };
  }, [game]);

  return gameTimeStatus;
};

/**
 * Get game status for display
 */
export const useGameStatus = (game: Game | null) => {
  return useMemo(() => {
    if (!game) {
      return { label: 'Unknown', color: 'text-gray-400', icon: '❓' };
    }

    const now = new Date();
    const gameStart = parseISO(game.game_date);
    const minutesToGame = differenceInMinutes(gameStart, now);

    // Game hasn't started yet
    if (game.status === 'scheduled') {
      if (minutesToGame > 0 && minutesToGame < 60) {
        return { label: `Starting in ${minutesToGame}m`, color: 'text-yellow-500', icon: '⏰' };
      }
      if (minutesToGame <= 0 && minutesToGame > -5) {
        return { label: 'Starting Soon', color: 'text-brand-600', icon: '🔴' };
      }
      return { label: 'Scheduled', color: 'text-gray-400', icon: '📅' };
    }

    // Game is live
    if (game.status === 'in_progress') {
      const periodDisplay = game.period ? (game.period <= 4 ? `Q${game.period}` : `OT${game.period - 4}`) : '';
      return {
        label: game.time_remaining ? `${periodDisplay} ${game.time_remaining}` : 'Live',
        color: 'text-brand-600 animate-pulse',
        icon: '🔴',
      };
    }

    // Game is final
    if (game.status === 'final') {
      return { label: 'Final', color: 'text-gray-300', icon: '✓' };
    }

    // Game is cancelled
    if (game.status === 'cancelled') {
      return { label: 'Cancelled', color: 'text-red-500', icon: '✕' };
    }

    return { label: 'Unknown', color: 'text-gray-400', icon: '❓' };
  }, [game]);
};

/**
 * Filter games by status
 */
export const useFilterGames = (games: Game[]) => {
  return useMemo(() => {
    const now = new Date();
    const today = now.toDateString();

    const live = games.filter(g => g.status === 'in_progress');
    const upcoming = games.filter(g => {
      const gameDate = parseISO(g.game_date);
      return g.status === 'scheduled' && (gameDate.toDateString() === today || isAfter(gameDate, now));
    });
    const completed = games.filter(g => g.status === 'final');

    return {
      live,
      upcoming,
      completed,
      hasLiveGames: live.length > 0,
      hasUpcomingGames: upcoming.length > 0,
    };
  }, [games]);
};

/**
 * Get games grouped by date
 */
export const useGroupGamesByDate = (games: Game[]) => {
  return useMemo(() => {
    const grouped: Record<string, Game[]> = {};

    games.forEach(game => {
      const date = parseISO(game.game_date).toDateString();
      if (!grouped[date]) {
        grouped[date] = [];
      }
      grouped[date].push(game);
    });

    // Sort dates (most recent first)
    const sortedDates = Object.keys(grouped).sort((a, b) => {
      return new Date(b).getTime() - new Date(a).getTime();
    });

    return sortedDates.map(date => ({
      date,
      games: grouped[date],
    }));
  }, [games]);
};

/**
 * Check if a game is currently in "crunch time" (last 2 minutes)
 */
export const useIsCrunchTime = (game: Game | null): boolean => {
  return useMemo(() => {
    if (!game || game.status !== 'in_progress') {
      return false;
    }

    // Check if 4th quarter and under 2 minutes
    if (game.period === 4 && game.time_remaining) {
      const timeParts = game.time_remaining.split(':');
      if (timeParts.length === 2) {
        const minutes = parseInt(timeParts[0], 10);
        const seconds = parseInt(timeParts[1], 10);
        return minutes < 2 || (minutes === 2 && seconds === 0);
      }
    }

    return false;
  }, [game]);
};

/**
 * Calculate when to next poll for a game
 */
export const useNextPollTime = (game: Game | null, currentTime: Date = new Date()): Date | null => {
  return useMemo(() => {
    if (!game) {
      return null;
    }

    const schedule = useGameSchedule(game);
    const gameStart = parseISO(game.game_date);

    // If game is scheduled and we need to poll predictions
    if (schedule.shouldPollPredictions) {
      return addMinutes(currentTime, 5); // Poll every 5 min before game
    }

    // If game is live
    if (schedule.shouldPollGameStatus) {
      return addMinutes(currentTime, schedule.gameStatusInterval / 60000);
    }

    // If game is upcoming (within 60 min)
    if (schedule.minutesToGame > 0 && schedule.minutesToGame <= 60) {
      return addMinutes(currentTime, 5);
    }

    return null;
  }, [game, currentTime]);
};

/**
 * Get optimal polling interval for multiple games
 */
export const useOptimalPollingInterval = (games: Game[]): number => {
  return useMemo(() => {
    if (games.length === 0) {
      return 3 * 60 * 1000; // Default 3 minutes
    }

    // Check if any game is in crunch time
    const anyInCrunchTime = games.some(game => {
      if (game.status !== 'in_progress') return false;
      if (game.period === 4 && game.time_remaining) {
        const timeParts = game.time_remaining.split(':');
        if (timeParts.length === 2) {
          const minutes = parseInt(timeParts[0], 10);
          return minutes < 2;
        }
      }
      return false;
    });

    if (anyInCrunchTime) {
      return 30 * 1000; // 30 seconds
    }

    // Check if any game is live
    const anyLive = games.some(g => g.status === 'in_progress');
    if (anyLive) {
      return 3 * 60 * 1000; // 3 minutes
    }

    // Check if any game is starting soon (within 30 min)
    const now = new Date();
    const anyStartingSoon = games.some(game => {
      if (game.status !== 'scheduled') return false;
      const gameStart = parseISO(game.game_date);
      const minutesToGame = differenceInMinutes(gameStart, now);
      return minutesToGame > 0 && minutesToGame <= 30;
    });

    if (anyStartingSoon) {
      return 60 * 1000; // 1 minute
    }

    return 5 * 60 * 1000; // Default 5 minutes
  }, [games]);
};

/**
 * Get games that need polling
 */
export const useGamesNeedingPolling = (games: Game[]) => {
  return useMemo(() => {
    const now = new Date();

    return games.filter(game => {
      const schedule = useGameSchedule(game);

      // Include if:
      // - Live game
      // - Starting within 30 minutes
      // - Scheduled to poll predictions
      // - Scheduled to poll injuries

      return (
        schedule.shouldPollGameStatus ||
        schedule.shouldPollPredictions ||
        schedule.shouldPollInjuries ||
        (schedule.minutesToGame > 0 && schedule.minutesToGame <= 30)
      );
    });
  }, [games]);
};

/**
 * Check if we should reduce polling (e.g., tab hidden, extended inactivity)
 */
export const useReducePolling = (): boolean => {
  if (typeof document === 'undefined') {
    return false;
  }

  // Check if page is hidden
  const isHidden = document.hidden;

  // Could add more conditions here (e.g., extended inactivity)
  return isHidden;
};
