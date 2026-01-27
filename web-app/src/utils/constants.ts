// ============================================================================
// Constants - NBA teams, colors, API configuration
// ============================================================================

import type { NBATeam } from '@/types/api.types';

// ============================================================================
// API Configuration
// ============================================================================

export const API_BASE_URL = import.meta.env.PUBLIC_API_BASE_URL || 'http://89.117.150.95:8001';

export const API_ENDPOINTS = {
  // Teams & Players
  TEAMS_LIST: '/api/nba/players/teams/list',
  PLAYERS_SEARCH: '/api/nba/players/search',
  PLAYER_STATS: '/api/nba/players/stats',

  // Games
  GAMES_LIST: '/api/nba/data/games',
  GAME_LINEUPS: '/api/nba/lineups/game',
  GAME_PREDICTIONS: '/api/nba/predictions/game',

  // Predictions
  PREDICTIONS_TOP: '/api/nba/predictions/top',
  PREDICTIONS_WITH_ODDS: '/api/nba/odds/predictions/with-odds',
  PREDICTIONS_PLAYER: '/api/nba/predictions/player',

  // Injuries
  INJURIES_LIST: '/api/nba/injuries',

  // Odds
  ODDS_LIVE: '/api/nba/odds/live',
  ODDS_HISTORICAL: '/api/nba/odds/historical',

  // Parlays
  PARLAYS_TOP_EV: '/api/parlays/top-ev',
  PARLAYS_SAME_GAME: '/api/nba/parlays/generate/same-game',

  // Sync
  SYNC_STATUS: '/api/sync/status',
  SYNC_TRIGGER: '/api/sync/trigger',
} as const;

// ============================================================================
// Polling Configuration (in milliseconds)
// ============================================================================

export const POLLING_INTERVALS = {
  GAME_STATUS_NORMAL: 3 * 60 * 1000, // 3 minutes
  GAME_STATUS_END_GAME: 30 * 1000, // 30 seconds (last 2 minutes)
  PREDICTIONS: 30 * 60 * 1000, // 30 minutes before game
  INJURIES: 10 * 60 * 1000, // 10 minutes
  SYNC_STATUS: 60 * 1000, // 1 minute
} as const;

export const GAME_TIME_THRESHOLDS = {
  PREDICTIONS_FETCH: 30, // minutes before game
  INJURIES_START: 60, // minutes before game
  END_GAME_WINDOW: 2, // minutes remaining in game
} as const;

// ============================================================================
// NBA Teams
// ============================================================================

export const NBA_TEAMS: NBATeam[] = [
  // Eastern Conference - Atlantic
  { id: 'bos', team_id: 1, abbreviation: 'BOS', city: 'Boston', nickname: 'Celtics', full_name: 'Boston Celtics', conference: 'East', division: 'Atlantic' },
  { id: 'bkn', team_id: 2, abbreviation: 'BKN', city: 'Brooklyn', nickname: 'Nets', full_name: 'Brooklyn Nets', conference: 'East', division: 'Atlantic' },
  { id: 'nyk', team_id: 3, abbreviation: 'NYK', city: 'New York', nickname: 'Knicks', full_name: 'New York Knicks', conference: 'East', division: 'Atlantic' },
  { id: 'phi', team_id: 4, abbreviation: 'PHI', city: 'Philadelphia', nickname: '76ers', full_name: 'Philadelphia 76ers', conference: 'East', division: 'Atlantic' },
  { id: 'tor', team_id: 5, abbreviation: 'TOR', city: 'Toronto', nickname: 'Raptors', full_name: 'Toronto Raptors', conference: 'East', division: 'Atlantic' },

  // Eastern Conference - Central
  { id: 'chi', team_id: 6, abbreviation: 'CHI', city: 'Chicago', nickname: 'Bulls', full_name: 'Chicago Bulls', conference: 'East', division: 'Central' },
  { id: 'cle', team_id: 7, abbreviation: 'CLE', city: 'Cleveland', nickname: 'Cavaliers', full_name: 'Cleveland Cavaliers', conference: 'East', division: 'Central' },
  { id: 'det', team_id: 8, abbreviation: 'DET', city: 'Detroit', nickname: 'Pistons', full_name: 'Detroit Pistons', conference: 'East', division: 'Central' },
  { id: 'ind', team_id: 9, abbreviation: 'IND', city: 'Indiana', nickname: 'Pacers', full_name: 'Indiana Pacers', conference: 'East', division: 'Central' },
  { id: 'mil', team_id: 10, abbreviation: 'MIL', city: 'Milwaukee', nickname: 'Bucks', full_name: 'Milwaukee Bucks', conference: 'East', division: 'Central' },

  // Eastern Conference - Southeast
  { id: 'atl', team_id: 11, abbreviation: 'ATL', city: 'Atlanta', nickname: 'Hawks', full_name: 'Atlanta Hawks', conference: 'East', division: 'Southeast' },
  { id: 'cha', team_id: 12, abbreviation: 'CHA', city: 'Charlotte', nickname: 'Hornets', full_name: 'Charlotte Hornets', conference: 'East', division: 'Southeast' },
  { id: 'mia', team_id: 13, abbreviation: 'MIA', city: 'Miami', nickname: 'Heat', full_name: 'Miami Heat', conference: 'East', division: 'Southeast' },
  { id: 'orl', team_id: 14, abbreviation: 'ORL', city: 'Orlando', nickname: 'Magic', full_name: 'Orlando Magic', conference: 'East', division: 'Southeast' },
  { id: 'was', team_id: 15, abbreviation: 'WAS', city: 'Washington', nickname: 'Wizards', full_name: 'Washington Wizards', conference: 'East', division: 'Southeast' },

  // Western Conference - Northwest
  { id: 'den', team_id: 16, abbreviation: 'DEN', city: 'Denver', nickname: 'Nuggets', full_name: 'Denver Nuggets', conference: 'West', division: 'Northwest' },
  { id: 'min', team_id: 17, abbreviation: 'MIN', city: 'Minnesota', nickname: 'Timberwolves', full_name: 'Minnesota Timberwolves', conference: 'West', division: 'Northwest' },
  { id: 'okc', team_id: 18, abbreviation: 'OKC', city: 'Oklahoma City', nickname: 'Thunder', full_name: 'Oklahoma City Thunder', conference: 'West', division: 'Northwest' },
  { id: 'por', team_id: 19, abbreviation: 'POR', city: 'Portland', nickname: 'Trail Blazers', full_name: 'Portland Trail Blazers', conference: 'West', division: 'Northwest' },
  { id: 'uta', team_id: 20, abbreviation: 'UTA', city: 'Utah', nickname: 'Jazz', full_name: 'Utah Jazz', conference: 'West', division: 'Northwest' },

  // Western Conference - Pacific
  { id: 'gsw', team_id: 21, abbreviation: 'GSW', city: 'Golden State', nickname: 'Warriors', full_name: 'Golden State Warriors', conference: 'West', division: 'Pacific' },
  { id: 'lac', team_id: 22, abbreviation: 'LAC', city: 'Los Angeles', nickname: 'Clippers', full_name: 'Los Angeles Clippers', conference: 'West', division: 'Pacific' },
  { id: 'lal', team_id: 23, abbreviation: 'LAL', city: 'Los Angeles', nickname: 'Lakers', full_name: 'Los Angeles Lakers', conference: 'West', division: 'Pacific' },
  { id: 'phx', team_id: 24, abbreviation: 'PHX', city: 'Phoenix', nickname: 'Suns', full_name: 'Phoenix Suns', conference: 'West', division: 'Pacific' },
  { id: 'sac', team_id: 25, abbreviation: 'SAC', city: 'Sacramento', nickname: 'Kings', full_name: 'Sacramento Kings', conference: 'West', division: 'Pacific' },

  // Western Conference - Southwest
  { id: 'dal', team_id: 26, abbreviation: 'DAL', city: 'Dallas', nickname: 'Mavericks', full_name: 'Dallas Mavericks', conference: 'West', division: 'Southwest' },
  { id: 'hou', team_id: 27, abbreviation: 'HOU', city: 'Houston', nickname: 'Rockets', full_name: 'Houston Rockets', conference: 'West', division: 'Southwest' },
  { id: 'mem', team_id: 28, abbreviation: 'MEM', city: 'Memphis', nickname: 'Grizzlies', full_name: 'Memphis Grizzlies', conference: 'West', division: 'Southwest' },
  { id: 'nop', team_id: 29, abbreviation: 'NOP', city: 'New Orleans', nickname: 'Pelicans', full_name: 'New Orleans Pelicans', conference: 'West', division: 'Southwest' },
  { id: 'sas', team_id: 30, abbreviation: 'SAS', city: 'San Antonio', nickname: 'Spurs', full_name: 'San Antonio Spurs', conference: 'West', division: 'Southwest' },
];

// Team abbreviation to full name mapping
export const TEAM_NAME_MAP: Record<string, string> = Object.fromEntries(
  NBA_TEAMS.map(team => [team.abbreviation, team.full_name])
);

// Team colors (primary, secondary)
export const TEAM_COLORS: Record<string, { primary: string; secondary: string }> = {
  BOS: { primary: '#007A33', secondary: '#BA9653' },
  BKN: { primary: '#000000', secondary: '#FFFFFF' },
  NYK: { primary: '#F58426', secondary: '#006BB6' },
  PHI: { primary: '#006BB6', secondary: '#ED174C' },
  TOR: { primary: '#CE1141', secondary: '#000000' },
  CHI: { primary: '#CE1141', secondary: '#000000' },
  CLE: { primary: '#860038', secondary: '#FDBB30' },
  DET: { primary: '#C8102E', secondary: '#00539B' },
  IND: { primary: '#002D62', secondary: '#FDBB30' },
  MIL: { primary: '#00471B', secondary: '#EEE1C6' },
  ATL: { primary: '#E03A3E', secondary: '#000000' },
  CHA: { primary: '#1D1160', secondary: '#008CA8' },
  MIA: { primary: '#98002E', secondary: '#F9A01B' },
  ORL: { primary: '#0077C0', secondary: '#000000' },
  WAS: { primary: '#002B5C', secondary: '#E31837' },
  DEN: { primary: '#0E2240', secondary: '#FDB927' },
  MIN: { primary: '#0C2340', secondary: '#23C372' },
  OKC: { primary: '#007AC1', secondary: '#EF3B24' },
  POR: { primary: '#E03A3E', secondary: '#000000' },
  UTA: { primary: '#002B5C', secondary: '#FDB927' },
  GSW: { primary: '#1D428A', secondary: '#FDB927' },
  LAC: { primary: '#C8102E', secondary: '#006BB6' },
  LAL: { primary: '#552583', secondary: '#FDB927' },
  PHX: { primary: '#E56020', secondary: '#000000' },
  SAC: { primary: '#5A2D81', secondary: '#000000' },
  DAL: { primary: '#00538C', secondary: '#00538C' },
  HOU: { primary: '#CE1141', secondary: '#000000' },
  MEM: { primary: '#5D76A9', secondary: '#12173F' },
  NOP: { primary: '#0C2340', secondary: '#F58426' },
  SAS: { primary: '#C4CED4', secondary: '#000000' },
};

// ============================================================================
// Stat Type Configuration
// ============================================================================

export const STAT_TYPES = {
  POINTS: 'points',
  REBOUNDS: 'rebounds',
  ASSISTS: 'assists',
  THREES: 'threes',
  PRA: 'pra', // Points + Rebounds + Assists
  PR: 'pr', // Points + Rebounds
  PA: 'pa', // Points + Assists
} as const;

export const STAT_LABELS: Record<string, string> = {
  points: 'PTS',
  rebounds: 'REB',
  assists: 'AST',
  threes: '3PT',
  pra: 'PRA',
  pr: 'PR',
  pa: 'PA',
};

// ============================================================================
// Injury Status Configuration
// ============================================================================

export const INJURY_STATUSES = {
  OUT: 'out',
  DOUBTFUL: 'doubtful',
  QUESTIONABLE: 'questionable',
  DAY_TO_DAY: 'day-to-day',
  AVAILABLE: 'available',
} as const;

export const INJURY_STATUS_CONFIG: Record<string, { label: string; color: string; priority: number }> = {
  out: { label: 'OUT', color: 'bg-red-600', priority: 5 },
  doubtful: { label: 'DOUBTFUL', color: 'bg-orange-600', priority: 4 },
  questionable: { label: 'QUESTIONABLE', color: 'bg-yellow-600', priority: 3 },
  'day-to-day': { label: 'DAY-TO-DAY', color: 'bg-blue-600', priority: 2 },
  available: { label: 'AVAILABLE', color: 'bg-green-600', priority: 1 },
};

// ============================================================================
// Game Status Configuration
// ============================================================================

export const GAME_STATUSES = {
  SCHEDULED: 'scheduled',
  IN_PROGRESS: 'in_progress',
  FINAL: 'final',
  CANCELLED: 'cancelled',
} as const;

export const GAME_STATUS_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  scheduled: { label: 'Scheduled', color: 'text-gray-400', icon: '📅' },
  in_progress: { label: 'Live', color: 'text-brand-600', icon: '🔴' },
  final: { label: 'Final', color: 'text-gray-300', icon: '✓' },
  cancelled: { label: 'Cancelled', color: 'text-red-500', icon: '✕' },
};

// ============================================================================
// Confidence Levels
// ============================================================================

export const CONFIDENCE_LEVELS = {
  HIGH: 0.75,
  MEDIUM: 0.5,
  LOW: 0.25,
} as const;

export const getConfidenceLabel = (confidence: number): string => {
  if (confidence >= CONFIDENCE_LEVELS.HIGH) return 'High';
  if (confidence >= CONFIDENCE_LEVELS.MEDIUM) return 'Medium';
  return 'Low';
};

export const getConfidenceColor = (confidence: number): string => {
  if (confidence >= CONFIDENCE_LEVELS.HIGH) return 'text-green-500';
  if (confidence >= CONFIDENCE_LEVELS.MEDIUM) return 'text-yellow-500';
  return 'text-red-500';
};

// ============================================================================
// Client-Side Routes
// ============================================================================

export const ROUTES = {
  HOME: '#/',
  TEAMS: '#/teams',
  TEAM_DETAIL: (teamId: string) => `#/team/${teamId}`,
  PREDICTIONS: '#/predictions',
  INJURIES: '#/injuries',
  PARLAYS: '#/parlays',
  GAME: (gameId: string) => `#/game/${gameId}`,
} as const;

// ============================================================================
// Pagination
// ============================================================================

export const DEFAULT_PAGE_SIZE = 20;

export const PAGE_SIZES = [10, 20, 50, 100] as const;

// ============================================================================
// Date Formats
// ============================================================================

export const DATE_FORMATS = {
  SHORT: 'M/d',
  MEDIUM: 'MMM d',
  LONG: 'MMMM d, yyyy',
  TIME: 'h:mm a',
  DATE_TIME: 'MMM d, h:mm a',
  ISO: "yyyy-MM-dd'T'HH:mm:ss",
} as const;

// ============================================================================
// Local Storage Keys
// ============================================================================

export const STORAGE_KEYS = {
  SELECTED_TEAM: 'nba_selected_team',
  FILTERS_PREDICTIONS: 'nba_filters_predictions',
  FILTERS_INJURIES: 'nba_filters_injuries',
  THEME: 'nba_theme',
} as const;

// ============================================================================
// Error Messages
// ============================================================================

export const ERROR_MESSAGES = {
  NETWORK_ERROR: 'Network error. Please check your connection.',
  API_ERROR: 'Failed to fetch data. Please try again.',
  NOT_FOUND: 'The requested data was not found.',
  UNAUTHORIZED: 'You are not authorized to access this data.',
  RATE_LIMIT: 'Too many requests. Please wait a moment.',
  GENERIC: 'Something went wrong. Please try again.',
} as const;

// ============================================================================
// ESPN-Inspired Theme Colors
// ============================================================================

export const THEME_COLORS = {
  brand: {
    50: '#fef2f2',
    100: '#fee2e2',
    200: '#fecaca',
    300: '#fca5a5',
    400: '#f87171',
    500: '#ef4444',
    600: '#dc2626', // ESPN Red
    700: '#b91c1c',
    800: '#991b1b',
    900: '#7f1d1d',
  },
  background: {
    primary: '#0b0f19', // Dark background
    secondary: '#111827', // Card background
    tertiary: '#1f2937', // Hover background
  },
  text: {
    primary: '#f9fafb', // White
    secondary: '#d1d5db', // Light gray
    tertiary: '#9ca3af', // Medium gray
    muted: '#6b7280', // Dark gray
  },
  border: {
    DEFAULT: '#374151', // Gray-700
    hover: '#4b5563', // Gray-600
  },
} as const;
