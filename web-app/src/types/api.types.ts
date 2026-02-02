// ============================================================================
// API Types - TypeScript interfaces matching backend models
// ============================================================================

// ============================================================================
// Team & Player Types
// ============================================================================

export interface NBAPlayer {
  id: string;
  player_id: number;
  first_name: string;
  last_name: string;
  full_name: string;
  team: string;
  position: string;
  height: string;
  weight: number;
  jersey_number: number;
  birth_date: string;
  country: string;
  season: string;
}

export interface NBATeam {
  id: string;
  team_id: number;
  abbreviation: string;
  city: string;
  nickname: string;
  full_name: string;
  conference: string;
  division: string;
}

export interface TeamRoster {
  team: NBATeam;
  players: NBAPlayer[];
}

// ============================================================================
// Game Types
// ============================================================================

export type GameStatus = 'scheduled' | 'in_progress' | 'final' | 'cancelled';

export interface Game {
  id: string;
  game_id: number;
  game_date: string;
  away_team: string;
  home_team: string;
  away_team_score: number | null;
  home_team_score: number | null;
  status: GameStatus;
  period: number | null;
  time_remaining: string | null;
  season: string;
}

export interface GameWithDetails extends Game {
  away_team_full: string;
  home_team_full: string;
  predictions?: Prediction[];
}

// ============================================================================
// Prediction Types
// ============================================================================

export type StatType = 'points' | 'rebounds' | 'assists' | 'threes' | 'pra' | 'pr' | 'pa';

export type Recommendation = 'OVER' | 'UNDER' | 'NONE';

export interface Prediction {
  id: string;
  prediction_id: string;
  player_id: string;
  player_name: string;
  team: string;
  game_id: string;
  stat_type: StatType;
  predicted_value: number;
  bookmaker_line: number | null;
  recommendation: Recommendation;
  confidence: number;
  over_price: number | null;
  under_price: number | null;
  odds_last_updated: string | null;
  created_at: string;
  game_date: string;
  opponent?: string;
  is_home?: boolean;
}

export interface PredictionWithOdds extends Prediction {
  home_team: string;
  away_team: string;
  game_date: string;
}

export interface TopPrediction {
  prediction: Prediction;
  expected_value: number;
  edge_percentage: number;
}

// ============================================================================
// Injury Types
// ============================================================================

export type InjuryStatus = 'out' | 'doubtful' | 'questionable' | 'day-to-day' | 'available';

export interface Injury {
  id: string;
  player_id: string;
  player_name: string;
  team: string;
  status: InjuryStatus;
  injury_type: string;
  impact_description: string;
  game_date: string | null;
  updated_at: string;
}

// ============================================================================
// Parlay Types
// ============================================================================

export interface ParlayLeg {
  player_id: string;
  player_name: string;
  team: string;
  stat_type: StatType;
  line: number;
  selection: 'OVER' | 'UNDER';
  odds: number;
}

export interface Parlay {
  id: string;
  legs: ParlayLeg[];
  total_odds: number;
  combined_probability: number;
  expected_value: number;
  game_id?: string;
  game_date?: string;
  created_at: string;
}

export interface SameGameParlayRequest {
  game_id: string;
  max_legs?: number;
  min_combined_probability?: number;
}

// ============================================================================
// Odds Types
// ============================================================================

export interface BookmakerOdds {
  bookmaker: string;
  last_updated: string;
  markets: Market[];
}

export interface Market {
  key: string;
  outcomes: Outcome[];
}

export interface Outcome {
  name: string;
  price: number;
  point?: number;
}

export interface PlayerOdds {
  player_id: string;
  player_name: string;
  team: string;
  stat_type: StatType;
  over_odds: number | null;
  under_odds: number | null;
  line: number | null;
  last_updated: string;
}

// ============================================================================
// Sync Status Types
// ============================================================================

export interface SyncStatus {
  is_syncing: boolean;
  last_sync: string | null;
  next_sync: string | null;
  sync_type: string | null;
  details: string | null;
}

// ============================================================================
// API Response Types
// ============================================================================

export interface ApiResponse<T> {
  data: T;
  success: boolean;
  message?: string;
}

export interface ApiError {
  detail: string;
  status_code: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ============================================================================
// Filter & Sort Types
// ============================================================================

export interface PredictionFilters {
  team?: string;
  statType?: StatType;
  minConfidence?: number;
  recommendation?: Recommendation;
  dateFrom?: string;
  dateTo?: string;
}

export interface InjuryFilters {
  team?: string;
  status?: InjuryStatus;
}

export interface GameFilters {
  team?: string;
  status?: GameStatus;
  dateFrom?: string;
  dateTo?: string;
}

// ============================================================================
// Game Time Calculation Types (for Smart Polling)
// ============================================================================

export interface GameTimeStatus {
  shouldPollPredictions: boolean;
  shouldPollInjuries: boolean;
  shouldPollGameStatus: boolean;
  gameStatusInterval: number;
  minutesToGame: number;
  isLastTwoMinutes: boolean;
  isGameToday: boolean;
}

// ============================================================================
// Store State Types
// ============================================================================

export interface TeamState {
  teams: NBATeam[];
  selectedTeam: NBATeam | null;
  roster: NBAPlayer[];
  loading: boolean;
  error: string | null;
}

export interface PredictionState {
  predictions: Prediction[];
  topPredictions: TopPrediction[];
  filteredPredictions: Prediction[];
  filters: PredictionFilters;
  loading: boolean;
  error: string | null;
}

export interface InjuryState {
  injuries: Injury[];
  filteredInjuries: Injury[];
  filters: InjuryFilters;
  loading: boolean;
  error: string | null;
}

export interface GameState {
  games: Game[];
  liveGames: Game[];
  upcomingGames: Game[];
  completedGames: Game[];
  loading: boolean;
  error: string | null;
  syncStatus: SyncStatus | null;
}

export interface AppSettings {
  apiBaseUrl: string;
  isPollingEnabled: boolean;
  pollingIntervals: {
    gameStatusNormal: number;
    gameStatusEndGame: number;
    predictions: number;
    injuries: number;
  };
}
