// ============================================================================
// useSmartPolling Hook - Context-aware polling for live updates
// ============================================================================

import { useEffect, useRef, useCallback, useState } from 'react';
import { useGameSchedule, useOptimalPollingInterval, useReducePolling } from './useGameSchedule';
import type { Game } from '@/types/api.types';
import { POLLING_INTERVALS } from '@/utils/constants';

// ============================================================================
// Polling State
// ============================================================================

interface PollingState {
  isPolling: boolean;
  lastPollTime: Date | null;
  nextPollTime: Date | null;
  pollCount: number;
  errorCount: number;
}

// ============================================================================
// Smart Polling Hook Options
// ============================================================================

interface SmartPollingOptions {
  /** Games to monitor for polling decisions */
  games?: Game[];
  /** Custom polling interval (overrides smart polling) */
  fixedInterval?: number;
  /** Whether polling is enabled */
  enabled?: boolean;
  /** Function to call on each poll */
  onPoll?: () => void | Promise<void>;
  /** Function to call when polling starts */
  onStart?: () => void;
  /** Function to call when polling stops */
  onStop?: () => void;
  /** Function to call on error */
  onError?: (error: Error) => void;
  /** Maximum number of consecutive errors before stopping */
  maxErrors?: number;
  /** Whether to pause polling when tab is hidden */
  pauseWhenHidden?: boolean;
}

// ============================================================================
// Main Smart Polling Hook
// ============================================================================

/**
 * Smart polling hook that adjusts polling intervals based on:
 * - Game context (scheduled, live, final)
 * - Time to game (30min, 60min thresholds)
 * - Game period (last 2 minutes vs normal)
 * - Page visibility (pause when hidden)
 */
export const useSmartPolling = (options: SmartPollingOptions = {}) => {
  const {
    games = [],
    fixedInterval,
    enabled = true,
    onPoll,
    onStart,
    onStop,
    onError,
    maxErrors = 5,
    pauseWhenHidden = true,
  } = options;

  // State
  const [pollingState, setPollingState] = useState<PollingState>({
    isPolling: false,
    lastPollTime: null,
    nextPollTime: null,
    pollCount: 0,
    errorCount: 0,
  });

  // Refs
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isPollingRef = useRef(false);
  const mountedRef = useRef(true);

  /**
   * Calculate optimal polling interval based on game context
   * (Made a plain function, not a hook dependency)
   */
  const calculateInterval = useCallback((): number => {
    // Use fixed interval if provided
    if (fixedInterval) {
      return fixedInterval;
    }

    // Use optimal interval based on games
    return useOptimalPollingInterval(games);
  }, [fixedInterval, games]);

  /**
   * Perform the poll
   */
  const doPoll = useCallback(async () => {
    if (!mountedRef.current || isPollingRef.current) {
      return;
    }

    isPollingRef.current = true;

    try {
      // Call the onPoll callback
      await onPoll?.();

      // Update state on success
      if (mountedRef.current) {
        setPollingState(prev => ({
          ...prev,
          lastPollTime: new Date(),
          errorCount: 0, // Reset error count on success
          pollCount: prev.pollCount + 1,
        }));
      }
    } catch (error) {
      // Handle error
      if (mountedRef.current) {
        const errorObj = error instanceof Error ? error : new Error('Polling error');
        setPollingState(prev => ({
          ...prev,
          errorCount: prev.errorCount + 1,
        }));

        // Call error callback
        onError?.(errorObj);

        // Stop polling if too many errors
        if (pollingState.errorCount + 1 >= maxErrors) {
          stopPolling();
          return;
        }
      }
    } finally {
      isPollingRef.current = false;
    }
  }, [onPoll, onError, maxErrors, pollingState.errorCount]);

  /**
   * Start polling
   */
  const startPolling = useCallback(() => {
    if (!enabled || !mountedRef.current) {
      return;
    }

    if (intervalRef.current) {
      // Already polling
      return;
    }

    onStart?.();

    const interval = calculateInterval();
    setPollingState(prev => ({
      ...prev,
      isPolling: true,
      nextPollTime: new Date(Date.now() + interval),
    }));

    intervalRef.current = setInterval(() => {
      doPoll();

      // Recalculate interval for next poll
      const newInterval = calculateInterval();
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = setInterval(() => doPoll(), newInterval);
      }

      setPollingState(prev => ({
        ...prev,
        nextPollTime: new Date(Date.now() + newInterval),
      }));
    }, interval);
  }, [enabled, calculateInterval, onStart, doPoll]);

  /**
   * Stop polling
   */
  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    isPollingRef.current = false;

    setPollingState(prev => ({
      ...prev,
      isPolling: false,
      nextPollTime: null,
    }));

    onStop?.();
  }, [onStop]);

  /**
   * Restart polling with new interval
   */
  const restartPolling = useCallback(() => {
    stopPolling();
    startPolling();
  }, [stopPolling, startPolling]);

  /**
   * Manually trigger a poll (without resetting interval)
   */
  const pollNow = useCallback(async () => {
    await doPoll();
  }, [doPoll]);

  // ============================================================================
  // Effects
  // ============================================================================

  /**
   * Main effect: Start/stop polling based on enabled state
   */
  useEffect(() => {
    // Only execute on client
    if (typeof window === 'undefined') {
      return;
    }

    if (!enabled) {
      stopPolling();
      return;
    }

    if (intervalRef.current) {
      return; // Already polling
    }

    onStart?.();

    const interval = calculateInterval();
    setPollingState({
      isPolling: true,
      lastPollTime: null,
      nextPollTime: new Date(Date.now() + interval),
      pollCount: 0,
      errorCount: 0,
    });

    intervalRef.current = setInterval(() => {
      (async () => {
        if (!mountedRef.current || isPollingRef.current) {
          return;
        }

        isPollingRef.current = true;

        try {
          await onPoll?.();

          if (mountedRef.current) {
            setPollingState(prev => ({
              ...prev,
              lastPollTime: new Date(),
              errorCount: 0,
              pollCount: prev.pollCount + 1,
            }));
          }
        } catch (error) {
          if (mountedRef.current) {
            const errorObj = error instanceof Error ? error : new Error('Polling error');
            setPollingState(prev => ({
              ...prev,
              errorCount: prev.errorCount + 1,
            }));

            onError?.(errorObj);

            if (pollingState.errorCount + 1 >= maxErrors) {
              stopPolling();
              return;
            }
          }
        } finally {
          isPollingRef.current = false;
        }
      })();
    }, interval);

    return () => {
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, fixedInterval, onPoll]);

  /**
   * Effect: Handle page visibility
   */
  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    if (!pauseWhenHidden) {
      return;
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        // Pause polling when tab is hidden
        if (intervalRef.current && !fixedInterval) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      } else {
        // Resume polling when tab is visible
        if (enabled && !intervalRef.current) {
          onStart?.();

          const interval = calculateInterval();
          intervalRef.current = setInterval(() => {
            (async () => {
              if (!mountedRef.current || isPollingRef.current) {
                return;
              }

              isPollingRef.current = true;

              try {
                await onPoll?.();

                if (mountedRef.current) {
                  setPollingState(prev => ({
                    ...prev,
                    lastPollTime: new Date(),
                    errorCount: 0,
                    pollCount: prev.pollCount + 1,
                  }));
                }
              } catch (error) {
                // Handle error silently
              } finally {
                isPollingRef.current = false;
              }
            })();
          }, interval);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [pauseWhenHidden, fixedInterval, enabled, onPoll]);

  /**
   * Effect: Cleanup on unmount
   */
  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    ...pollingState,
    startPolling,
    stopPolling,
    restartPolling,
    pollNow,
    interval: calculateInterval(),
  };
};

// ============================================================================
// Specialized Polling Hooks
// ============================================================================

/**
 * Poll for game status updates
 * Uses smart intervals based on game context
 */
export const useGameStatusPolling = (
  games: Game[],
  onPoll: () => void | Promise<void>,
  options: Omit<SmartPollingOptions, 'games' | 'onPoll'> = {}
) => {
  return useSmartPolling({
    games,
    onPoll,
    ...options,
  });
};

/**
 * Poll for prediction updates
 * Polls starting 30 minutes before game
 */
export const usePredictionPolling = (
  games: Game[],
  onPoll: () => void | Promise<void>,
  options: Omit<SmartPollingOptions, 'games' | 'onPoll'> = {}
) => {
  // Filter games that need prediction polling
  const gamesNeedingPolling = games.filter(game => {
    const schedule = useGameSchedule(game);
    return schedule.shouldPollPredictions;
  });

  return useSmartPolling({
    games: gamesNeedingPolling,
    fixedInterval: POLLING_INTERVALS.PREDICTIONS,
    onPoll,
    ...options,
  });
};

/**
 * Poll for injury updates
 * Polls starting 60 minutes before game
 */
export const useInjuryPolling = (
  games: Game[],
  onPoll: () => void | Promise<void>,
  options: Omit<SmartPollingOptions, 'games' | 'onPoll'> = {}
) => {
  // Filter games that need injury polling
  const gamesNeedingPolling = games.filter(game => {
    const schedule = useGameSchedule(game);
    return schedule.shouldPollInjuries;
  });

  return useSmartPolling({
    games: gamesNeedingPolling,
    fixedInterval: POLLING_INTERVALS.INJURIES,
    onPoll,
    ...options,
  });
};

/**
 * Poll for sync status
 * Regular polling to check backend sync status
 */
export const useSyncStatusPolling = (
  onPoll: () => void | Promise<void>,
  options: Omit<SmartPollingOptions, 'onPoll'> = {}
) => {
  return useSmartPolling({
    fixedInterval: POLLING_INTERVALS.SYNC_STATUS,
    onPoll,
    ...options,
  });
};

// ============================================================================
// Utility Hook: Poll a single endpoint
// ============================================================================

/**
 * Simple polling hook for a single async function
 */
export const useIntervalPolling = (
  pollFn: () => void | Promise<void>,
  interval: number,
  options: Pick<SmartPollingOptions, 'enabled' | 'pauseWhenHidden'> = {}
) => {
  const { enabled = true, pauseWhenHidden = true } = options;

  return useSmartPolling({
    enabled,
    pauseWhenHidden,
    fixedInterval: interval,
    onPoll: pollFn,
  });
};

// ============================================================================
// Export Types
// ============================================================================

export type { PollingState, SmartPollingOptions };
