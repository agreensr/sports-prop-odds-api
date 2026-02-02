// ============================================================================
// Formatters - Utility functions for formatting data
// ============================================================================

import { format, formatDistanceToNow, parseISO, isToday, isYesterday, isTomorrow } from 'date-fns';
import { STAT_LABELS, INJURY_STATUS_CONFIG, TEAM_NAME_MAP } from './constants';

// ============================================================================
// Date & Time Formatters
// ============================================================================

/**
 * Format a date string to a human-readable format
 */
export const formatDate = (dateString: string, formatStr: string = 'MMM d, yyyy'): string => {
  try {
    const date = parseISO(dateString);
    return format(date, formatStr);
  } catch {
    return dateString;
  }
};

/**
 * Format a game date with smart labels (Today, Tomorrow, etc.)
 */
export const formatGameDate = (dateString: string): string => {
  try {
    const date = parseISO(dateString);

    if (isToday(date)) {
      return `Today, ${format(date, 'h:mm a')}`;
    }
    if (isTomorrow(date)) {
      return `Tomorrow, ${format(date, 'h:mm a')}`;
    }
    if (isYesterday(date)) {
      return `Yesterday, ${format(date, 'h:mm a')}`;
    }

    return format(date, 'MMM d, h:mm a');
  } catch {
    return dateString;
  }
};

/**
 * Format relative time (e.g., "2 hours ago")
 */
export const formatRelativeTime = (dateString: string): string => {
  try {
    const date = parseISO(dateString);
    return formatDistanceToNow(date, { addSuffix: true });
  } catch {
    return dateString;
  }
};

/**
 * Format time only (e.g., "7:30 PM")
 */
export const formatTime = (dateString: string): string => {
  try {
    const date = parseISO(dateString);
    return format(date, 'h:mm a');
  } catch {
    return dateString;
  }
};

/**
 * Format time remaining in a game
 */
export const formatTimeRemaining = (period: number | null, timeRemaining: string | null): string => {
  if (!period || !timeRemaining) return '-';
  return `${period <= 4 ? `Q${period}` : `OT${period - 4}`} - ${timeRemaining}`;
};

// ============================================================================
// Number & Stat Formatters
// ============================================================================

/**
 * Format a number with specified decimal places
 */
export const formatNumber = (num: number, decimals: number = 1): string => {
  return num.toFixed(decimals);
};

/**
 * Format a stat type to its label
 */
export const formatStatType = (statType: string): string => {
  return STAT_LABELS[statType] || statType.toUpperCase();
};

/**
 * Format predicted value vs line comparison
 */
export const formatPredictionLine = (predicted: number, line: number | null): string => {
  if (line === null) return formatNumber(predicted);
  const diff = predicted - line;
  const sign = diff >= 0 ? '+' : '';
  return `${formatNumber(predicted)} vs ${formatNumber(line)} (${sign}${formatNumber(diff)})`;
};

// ============================================================================
// American Odds Formatters
// ============================================================================

/**
 * Convert American odds to decimal odds
 */
export const americanToDecimal = (americanOdds: number): number => {
  if (americanOdds > 0) {
    return (americanOdds / 100) + 1;
  }
  return (100 / Math.abs(americanOdds)) + 1;
};

/**
 * Convert American odds to implied probability
 */
export const americanToProbability = (americanOdds: number): number => {
  if (americanOdds > 0) {
    return 100 / (americanOdds + 100);
  }
  return Math.abs(americanOdds) / (Math.abs(americanOdds) + 100);
};

/**
 * Format American odds with sign
 */
export const formatAmericanOdds = (odds: number | null): string => {
  if (odds === null) return 'N/A';
  const sign = odds > 0 ? '+' : '';
  return `${sign}${odds}`;
};

/**
 * Calculate potential win amount from American odds
 */
export const calculateWinAmount = (stake: number, americanOdds: number): number => {
  if (americanOdds > 0) {
    return stake * (americanOdds / 100);
  }
  return stake * (100 / Math.abs(americanOdds));
};

/**
 * Calculate total payout (stake + winnings)
 */
export const calculatePayout = (stake: number, americanOdds: number): number => {
  return stake + calculateWinAmount(stake, americanOdds);
};

/**
 * Calculate Expected Value (EV)
 */
export const calculateEV = (odds: number, winProbability: number): number => {
  const decimalOdds = americanToDecimal(odds);
  return (winProbability * (decimalOdds - 1)) - (1 - winProbability);
};

/**
 * Calculate edge percentage
 */
export const calculateEdge = (trueProbability: number, impliedProbability: number): number => {
  return ((trueProbability - impliedProbability) / impliedProbability) * 100;
};

// ============================================================================
// Team & Player Formatters
// ============================================================================

/**
 * Get full team name from abbreviation
 */
export const getTeamFullName = (abbr: string): string => {
  return TEAM_NAME_MAP[abbr] || abbr;
};

/**
 * Format player name (First Last)
 */
export const formatPlayerName = (firstName: string, lastName: string): string => {
  return `${firstName} ${lastName}`;
};

/**
 * Get player initials
 */
export const getPlayerInitials = (firstName: string, lastName: string): string => {
  return `${firstName[0]}${lastName[0]}`.toUpperCase();
};

/**
 * Format position display
 */
export const formatPosition = (position: string): string => {
  const positionMap: Record<string, string> = {
    'PG': 'Point Guard',
    'SG': 'Shooting Guard',
    'SF': 'Small Forward',
    'PF': 'Power Forward',
    'C': 'Center',
    'G': 'Guard',
    'F': 'Forward',
    'GF': 'Guard-Forward',
    'FC': 'Forward-Center',
  };
  return positionMap[position] || position;
};

/**
 * Format height (inches to feet/inches)
 */
export const formatHeight = (heightInches: string): string => {
  const inches = parseInt(heightInches);
  if (isNaN(inches)) return heightInches;

  const feet = Math.floor(inches / 12);
  const remainingInches = inches % 12;
  return `${feet}-${remainingInches}"`;
};

/**
 * Format weight (lbs)
 */
export const formatWeight = (weight: number): string => {
  return `${weight} lbs`;
};

// ============================================================================
// Injury Formatters
// ============================================================================

/**
 * Get injury status config
 */
export const getInjuryStatusConfig = (status: string) => {
  return INJURY_STATUS_CONFIG[status] || {
    label: status.toUpperCase(),
    color: 'bg-gray-600',
    priority: 0,
  };
};

/**
 * Format injury description
 */
export const formatInjuryDescription = (injuryType: string, description: string | null): string => {
  if (description) return description;
  return injuryType;
};

// ============================================================================
// Confidence & Value Formatters
// ============================================================================

/**
 * Format confidence as percentage
 */
export const formatConfidence = (confidence: number): string => {
  return `${Math.round(confidence * 100)}%`;
};

/**
 * Format confidence with label
 */
export const formatConfidenceWithLabel = (confidence: number): string => {
  const percentage = Math.round(confidence * 100);
  if (percentage >= 75) return `${percentage}% (High)`;
  if (percentage >= 50) return `${percentage}% (Medium)`;
  return `${percentage}% (Low)`;
};

/**
 * Format edge percentage
 */
export const formatEdge = (edge: number): string => {
  const sign = edge >= 0 ? '+' : '';
  return `${sign}${edge.toFixed(1)}%`;
};

/**
 * Format expected value
 */
export const formatEV = (ev: number): string => {
  const sign = ev >= 0 ? '+' : '';
  return `${sign}${ev.toFixed(2)}`;
};

// ============================================================================
// Game Score Formatters
// ============================================================================

/**
 * Format game score display
 */
export const formatGameScore = (
  awayTeam: string,
  homeTeam: string,
  awayScore: number | null,
  homeScore: number | null,
  status: string
): string => {
  const awayAbbr = awayTeam;
  const homeAbbr = homeTeam;

  if (status === 'scheduled') {
    return `${awayAbbr} vs ${homeAbbr}`;
  }

  if (awayScore === null || homeScore === null) {
    return `${awayAbbr} vs ${homeAbbr}`;
  }

  return `${awayAbbr} ${awayScore} - ${homeScore} ${homeAbbr}`;
};

/**
 * Format game period display
 */
export const formatGamePeriod = (period: number | null, status: string): string => {
  if (status === 'scheduled') return 'Scheduled';
  if (status === 'final') return 'Final';
  if (status === 'cancelled') return 'Cancelled';
  if (!period) return 'Live';

  if (period <= 4) {
    return `Q${period}`;
  }
  return `OT${period - 4}`;
};

// ============================================================================
// Parlay Formatters
// ============================================================================

/**
 * Calculate parlay odds from legs
 */
export const calculateParlayOdds = (legOdds: number[]): number => {
  const decimalOdds = legOdds.map(americanToDecimal);
  const totalDecimal = decimalOdds.reduce((acc, odds) => acc * odds, 1);

  // Convert back to American odds
  if (totalDecimal >= 2) {
    return Math.round((totalDecimal - 1) * 100);
  }
  return Math.round(-100 / (totalDecimal - 1));
};

/**
 * Format parlay legs display
 */
export const formatParlayLegs = (legs: number): string => {
  return `${legs} Leg${legs > 1 ? 's' : ''}`;
};

// ============================================================================
// URL & Route Formatters
// ============================================================================

/**
 * Build query string from object
 */
export const buildQueryString = (params: Record<string, string | number | boolean | undefined>): string => {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.set(key, String(value));
    }
  });
  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : '';
};

/**
 * Parse query string to object
 */
export const parseQueryString = (queryString: string): Record<string, string> => {
  const searchParams = new URLSearchParams(queryString);
  const result: Record<string, string> = {};
  searchParams.forEach((value, key) => {
    result[key] = value;
  });
  return result;
};

// ============================================================================
// Conditional Formatting
// ============================================================================

/**
 * Get CSS class based on value comparison
 */
export const getValueColor = (value: number, baseline: number): string => {
  if (value > baseline) return 'text-green-500';
  if (value < baseline) return 'text-red-500';
  return 'text-gray-400';
};

/**
 * Get CSS class for recommendation
 */
export const getRecommendationColor = (recommendation: string): string => {
  switch (recommendation) {
    case 'OVER':
      return 'text-green-500';
    case 'UNDER':
      return 'text-red-500';
    default:
      return 'text-gray-400';
  }
};

/**
 * Get recommendation badge style
 */
export const getRecommendationBadgeStyle = (recommendation: string): string => {
  switch (recommendation) {
    case 'OVER':
      return 'bg-green-600/20 text-green-400 border-green-600/30';
    case 'UNDER':
      return 'bg-red-600/20 text-red-400 border-red-600/30';
    default:
      return 'bg-gray-600/20 text-gray-400 border-gray-600/30';
  }
};

// ============================================================================
// Validation & Sanitization
// ============================================================================

/**
 * Sanitize user input to prevent XSS
 */
export const sanitizeInput = (input: string): string => {
  const div = document.createElement('div');
  div.textContent = input;
  return div.innerHTML;
};

/**
 * Validate email format
 */
export const isValidEmail = (email: string): boolean => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
};

/**
 * Validate team abbreviation
 */
export const isValidTeamAbbr = (abbr: string): boolean => {
  return abbr in TEAM_NAME_MAP;
};

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Truncate text with ellipsis
 */
export const truncateText = (text: string, maxLength: number): string => {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 3)}...`;
};

/**
 * Pluralize a word based on count
 */
export const pluralize = (word: string, count: number): string => {
  return count === 1 ? word : `${word}s`;
};

/**
 * Debounce function
 */
export const debounce = <T extends (...args: unknown[]) => unknown>(
  func: T,
  delay: number
): ((...args: Parameters<T>) => void) => {
  let timeoutId: ReturnType<typeof setTimeout>;
  return (...args: Parameters<T>) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => func(...args), delay);
  };
};

/**
 * Throttle function
 */
export const throttle = <T extends (...args: unknown[]) => unknown>(
  func: T,
  limit: number
): ((...args: Parameters<T>) => void) => {
  let inThrottle: boolean;
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
};

/**
 * Generate a unique ID
 */
export const generateId = (): string => {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
};

/**
 * Deep clone an object
 */
export const deepClone = <T>(obj: T): T => {
  return JSON.parse(JSON.stringify(obj));
};

/**
 * Check if running in development mode
 */
export const isDevelopment = (): boolean => {
  return import.meta.env.DEV;
};

/**
 * Check if running in production mode
 */
export const isProduction = (): boolean => {
  return import.meta.env.PROD;
};

/**
 * Get environment variable with fallback
 */
export const getEnvVar = (key: string, fallback: string = ''): string => {
  return import.meta.env[key] || fallback;
};
