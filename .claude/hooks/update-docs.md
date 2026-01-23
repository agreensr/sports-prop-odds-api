---
description: Update all project .md documentation files to reflect current codebase
trigger:
  type: command
  pattern: "^/update-docs"
---
- name: explore_codebase
  prompt: |
    Explore the sports-bet-ai-api codebase thoroughly to document:

    1. All API endpoints (routes, methods, parameters)
    2. Database models and their relationships
    3. Services and their functionality
    4. Scripts and cron jobs
    5. Project structure and architecture
    6. Recent features added (injury tracking, lineup tracking, parlay system, bet tracking)
    7. Current tech stack and dependencies

    Search through:
    - app/api/routes/ for all route definitions
    - app/models/ for database models
    - app/services/ for service implementations
    - scripts/ for automation scripts
    - migrations/ for database schema changes
    - app/main.py for application configuration

    Return a comprehensive summary of:
    - Current API endpoints with their methods, paths, and purposes
    - Database tables and their columns
    - Services and what they do
    - Automation scripts and their schedules
    - Recent features with their implementation details
    - Architecture and data flow
- name: update_readme
  prompt: |
    Update the README.md file to reflect the current state of the codebase.

    Use the exploration results to create a comprehensive README that includes:

    1. Updated project description with current features
    2. Complete project structure reflecting new directories and files
    3. All API endpoints organized by category:
       - Predictions endpoints
       - Players endpoints
       - Odds endpoints
       - Injury endpoints
       - Lineup endpoints
       - Parlay endpoints
       - Bet tracking endpoints
       - Data management endpoints
       - Health/check endpoints
    4. Database models section with tables:
       - Player, Game, Prediction
       - PlayerStats, GameOdds
       - PlayerInjury (injury tracking)
       - ExpectedLineup (lineup projections)
       - Parlay, ParlayLeg (parlay system)
       - PlacedBet, PlacedBetLeg (bet tracking)
    5. Services section explaining:
       - PredictionService (injury-aware, per-36 stats)
       - InjuryService (ESPN + Firecrawl)
       - LineupService (Rotowire scraping)
       - ParlayService (EV calculation)
       - BetTrackingService
    6. Automation scripts and cron jobs
    7. Tech stack with all dependencies
    8. VPS setup and deployment instructions
    9. Recent features section highlighting:
       - Injury & lineup tracking
       - Parlay generation with corrected EV
       - Bet tracking
       - Accuracy tracking
    10. API documentation link

    Use proper markdown formatting with code blocks, tables, and sections.
    Keep the tone professional and clear.
- name: update_prd
  prompt: |
    Update the PRD.md (Product Requirements Document) to reflect current implementation status.

    Update the following sections based on exploration:

    1. Development Roadmap - mark completed items:
       - Phase 3: Odds Integration → mark as COMPLETE
       - Add injury/lineup tracking to completed phases
       - Add parlay system to completed phases
       - Add bet tracking to completed phases
    2. Core Features - add new features:
       - Injury & Lineup Tracking
       - Parlay Generation with EV calculation
       - Bet Tracking & Result Verification
       - Accuracy Tracking System
    3. API Architecture - add new endpoints:
       - /api/injuries/*
       - /api/lineups/*
       - /api/parlays/*
       - /api/bets/*
       - /api/accuracy/*
    4. Database Schema - add new tables:
       - player_injuries
       - expected_lineups
       - parlays, parlay_legs
       - placed_bets, placed_bet_legs
    5. Tech Stack - add new dependencies
    6. Success Metrics - update based on current capabilities
    7. Change Log - add recent updates

    Maintain the existing format and structure.
- name: commit_updates
  prompt: |
    After updating the .md files, show a summary of what was changed and offer to commit the changes.

    List the files that were modified and the key updates made to each.
    Then ask if the user wants to commit these documentation updates.
