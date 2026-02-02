// ============================================================================
// API Client - Base HTTP client with error handling
// ============================================================================

import { API_BASE_URL, API_ENDPOINTS, ERROR_MESSAGES } from '@/utils/constants';
import type {
  ApiResponse,
  ApiError,
  NBAPlayer,
  NBATeam,
  Game,
  Prediction,
  TopPrediction,
  Injury,
  Parlay,
  SyncStatus,
} from '@/types/api.types';

// ============================================================================
// Error Classes
// ============================================================================

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public detail?: string
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

export class NetworkError extends Error {
  constructor(message: string = ERROR_MESSAGES.NETWORK_ERROR) {
    super(message);
    this.name = 'NetworkError';
  }
}

// ============================================================================
// API Client Class
// ============================================================================

class ApiClient {
  private baseUrl: string;
  private defaultHeaders: Record<string, string>;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
    this.defaultHeaders = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
  }

  /**
   * Build full URL from endpoint
   */
  private buildUrl(endpoint: string, params?: Record<string, string | number>): string {
    const url = new URL(endpoint, this.baseUrl);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.set(key, String(value));
        }
      });
    }
    return url.toString();
  }

  /**
   * Handle API response
   */
  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      let errorMessage: string = ERROR_MESSAGES.API_ERROR;
      let errorDetail: string | undefined;

      try {
        const errorData: ApiError = await response.json();
        errorMessage = errorData.detail || errorMessage;
        errorDetail = errorData.detail;
      } catch {
        // If parsing fails, use status text
        errorMessage = response.statusText || errorMessage;
      }

      throw new ApiRequestError(errorMessage, response.status, errorDetail);
    }

    // Handle empty responses (e.g., 204 No Content)
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      return undefined as unknown as T;
    }

    return response.json();
  }

  /**
   * Make HTTP request
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    params?: Record<string, string | number>
  ): Promise<T> {
    const url = this.buildUrl(endpoint, params);

    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          ...this.defaultHeaders,
          ...options.headers,
        },
      });

      return await this.handleResponse<T>(response);
    } catch (error) {
      if (error instanceof ApiRequestError) {
        throw error;
      }

      // Network errors (CORS, offline, etc.)
      throw new NetworkError(ERROR_MESSAGES.NETWORK_ERROR);
    }
  }

  /**
   * GET request
   */
  async get<T>(endpoint: string, params?: Record<string, string | number>): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' }, params);
  }

  /**
   * POST request
   */
  async post<T>(endpoint: string, data?: unknown, params?: Record<string, string | number>): Promise<T> {
    return this.request<T>(
      endpoint,
      {
        method: 'POST',
        body: JSON.stringify(data),
      },
      params
    );
  }

  /**
   * PUT request
   */
  async put<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  /**
   * DELETE request
   */
  async delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }
}

// ============================================================================
// API Client Instance
// ============================================================================

const apiClient = new ApiClient();

// ============================================================================
// API Methods - Teams & Players
// ============================================================================

export const teamsApi = {
  /**
   * Get list of all NBA teams
   */
  getTeams: (): Promise<NBATeam[]> => {
    return apiClient.get<NBATeam[]>(API_ENDPOINTS.TEAMS_LIST);
  },

  /**
   * Get players by team (using search endpoint with team name)
   */
  getTeamPlayers: (teamName: string): Promise<NBAPlayer[]> => {
    return apiClient.get<NBAPlayer[]>(API_ENDPOINTS.PLAYERS_SEARCH, { name: teamName });
  },

  /**
   * Search players by name
   */
  searchPlayers: (query: string): Promise<NBAPlayer[]> => {
    return apiClient.get<NBAPlayer[]>(API_ENDPOINTS.PLAYERS_SEARCH, { name: query });
  },
};

// ============================================================================
// API Methods - Games
// ============================================================================

export const gamesApi = {
  /**
   * Get list of games with optional filters
   */
  getGames: (params?: {
    start_date?: string;
    end_date?: string;
    team?: string;
    status?: string;
  }): Promise<Game[]> => {
    return apiClient.get<Game[]>(API_ENDPOINTS.GAMES_LIST, params);
  },

  /**
   * Get today's games
   */
  getTodaysGames: (): Promise<Game[]> => {
    const today = new Date().toISOString().split('T')[0];
    return apiClient.get<Game[]>(API_ENDPOINTS.GAMES_LIST, {
      start_date: today,
      end_date: today,
    });
  },

  /**
   * Get game lineups
   */
  getGameLineups: (gameId: string): Promise<unknown> => {
    return apiClient.get(`${API_ENDPOINTS.GAME_LINEUPS}/${gameId}`);
  },

  /**
   * Get predictions for a specific game
   */
  getGamePredictions: (gameId: string): Promise<Prediction[]> => {
    return apiClient.get<Prediction[]>(`${API_ENDPOINTS.GAME_PREDICTIONS}/${gameId}`);
  },
};

// ============================================================================
// API Methods - Predictions
// ============================================================================

export const predictionsApi = {
  /**
   * Get top predictions
   */
  getTopPredictions: (params?: {
    limit?: number;
    min_confidence?: number;
  }): Promise<TopPrediction[]> => {
    return apiClient.get<TopPrediction[]>(API_ENDPOINTS.PREDICTIONS_TOP, params);
  },

  /**
   * Get predictions with odds
   */
  getPredictionsWithOdds: (params?: {
    game_date?: string;
    team?: string;
    min_confidence?: number;
  }): Promise<Prediction[]> => {
    return apiClient.get<Prediction[]>(API_ENDPOINTS.PREDICTIONS_WITH_ODDS, params);
  },

  /**
   * Get predictions for a specific player
   */
  getPlayerPredictions: (playerId: string): Promise<Prediction[]> => {
    return apiClient.get<Prediction[]>(`${API_ENDPOINTS.PREDICTIONS_PLAYER}/${playerId}`);
  },
};

// ============================================================================
// API Methods - Injuries
// ============================================================================

export const injuriesApi = {
  /**
   * Get all injuries
   */
  getInjuries: (params?: {
    team?: string;
    status?: string;
  }): Promise<Injury[]> => {
    return apiClient.get<Injury[]>(API_ENDPOINTS.INJURIES_LIST, params);
  },

  /**
   * Get injuries for a specific team
   */
  getTeamInjuries: (team: string): Promise<Injury[]> => {
    return apiClient.get<Injury[]>(API_ENDPOINTS.INJURIES_LIST, { team });
  },
};

// ============================================================================
// API Methods - Parlays
// ============================================================================

export const parlaysApi = {
  /**
   * Get top EV parlays
   */
  getTopEVParlays: (params?: {
    limit?: number;
    min_ev?: number;
  }): Promise<Parlay[]> => {
    return apiClient.get<Parlay[]>(API_ENDPOINTS.PARLAYS_TOP_EV, params);
  },

  /**
   * Generate same-game parlay
   */
  generateSameGameParlay: (gameId: string, options?: {
    max_legs?: number;
    min_combined_probability?: number;
  }): Promise<Parlay> => {
    return apiClient.post<Parlay>(
      `${API_ENDPOINTS.PARLAYS_SAME_GAME}/${gameId}`,
      options
    );
  },
};

// ============================================================================
// API Methods - Sync
// ============================================================================

export const syncApi = {
  /**
   * Get sync status
   */
  getSyncStatus: (): Promise<SyncStatus> => {
    return apiClient.get<SyncStatus>(API_ENDPOINTS.SYNC_STATUS);
  },

  /**
   * Trigger a manual sync
   */
  triggerSync: (syncType?: string): Promise<SyncStatus> => {
    return apiClient.post<SyncStatus>(
      API_ENDPOINTS.SYNC_TRIGGER,
      { sync_type: syncType }
    );
  },
};

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Check if API is available
 */
export const checkApiHealth = async (): Promise<boolean> => {
  try {
    await syncApi.getSyncStatus();
    return true;
  } catch {
    return false;
  }
};

/**
 * Get base URL for API
 */
export const getApiBaseUrl = (): string => {
  return API_BASE_URL;
};

// ============================================================================
// Export all APIs
// ============================================================================

export const api = {
  teams: teamsApi,
  games: gamesApi,
  predictions: predictionsApi,
  injuries: injuriesApi,
  parlays: parlaysApi,
  sync: syncApi,
};

export default apiClient;
