-- Create placed_bets table for tracking actual bets placed on sportsbooks
CREATE TABLE IF NOT EXISTS placed_bets (
    id VARCHAR(36) PRIMARY KEY,
    sportsbook VARCHAR(50) NOT NULL,
    bet_id VARCHAR(100) NOT NULL,
    bet_type VARCHAR(20) NOT NULL,
    game_id VARCHAR(36),
    matchup VARCHAR(100) NOT NULL,
    game_date TIMESTAMP NOT NULL,
    wager_amount FLOAT NOT NULL,
    total_charged FLOAT NOT NULL,
    odds INTEGER NOT NULL,
    to_win FLOAT NOT NULL,
    total_payout FLOAT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    cash_out_value FLOAT,
    actual_payout FLOAT,
    profit_loss FLOAT,
    placed_at TIMESTAMP NOT NULL,
    settled_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL
);

-- Create indexes
CREATE INDEX ix_placed_bets_sportsbook ON placed_bets(sportsbook);
CREATE INDEX ix_placed_bets_status ON placed_bets(status);
CREATE INDEX ix_placed_bets_game_date ON placed_bets(game_date);
CREATE INDEX ix_placed_bets_bet_id ON placed_bets(bet_id);
CREATE INDEX ix_placed_bets_game_id ON placed_bets(game_id);

-- Create placed_bet_legs table for tracking individual legs
CREATE TABLE IF NOT EXISTS placed_bet_legs (
    id VARCHAR(36) PRIMARY KEY,
    bet_id VARCHAR(36) NOT NULL,
    player_name VARCHAR(255) NOT NULL,
    player_team VARCHAR(10) NOT NULL,
    stat_type VARCHAR(50) NOT NULL,
    selection VARCHAR(10) NOT NULL,
    line FLOAT,
    special_bet VARCHAR(100),

    -- Model prediction tracking
    predicted_value FLOAT,
    model_confidence FLOAT,
    recommendation VARCHAR(10),

    -- Result tracking
    result VARCHAR(20),
    actual_value FLOAT,
    was_correct BOOLEAN,

    created_at TIMESTAMP NOT NULL,

    FOREIGN KEY (bet_id) REFERENCES placed_bets(id) ON DELETE CASCADE
);

-- Create indexes
CREATE INDEX ix_placed_bet_legs_bet_id ON placed_bet_legs(bet_id);
