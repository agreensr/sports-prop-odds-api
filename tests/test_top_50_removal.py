"""
Comprehensive tests to verify the Top 50 system has been completely removed.

This test suite verifies:
1. Top50Service cannot be imported
2. ParlayService works without top_50_player_ids parameter
3. Database table top_50_players does not exist
4. generate_smart_parlays.py script runs without Top 50
5. No references to top_50 in key files (except comments and migration files)
"""
import os
import sys
import subprocess
from pathlib import Path
import importlib

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestTop50ImportRemoval:
    """Test that Top50Service cannot be imported."""

    def test_top50_service_module_does_not_exist(self):
        """Verify the top_50_service.py file has been removed."""
        service_path = PROJECT_ROOT / "app" / "services" / "nba" / "top_50_service.py"

        assert not service_path.exists(), \
            f"Top50Service file still exists at {service_path}. It should be removed."

    def test_top50_service_cannot_be_imported(self):
        """Verify Top50Service cannot be imported from app.services.nba."""
        with pytest.raises(ImportError):
            from app.services.nba.top_50_service import Top50Service

    def test_top50_service_not_in_nba_services_init(self):
        """Verify Top50Service is not exported from app.services.nba."""
        from app.services import nba

        # Check that Top50Service is not in the module
        assert not hasattr(nba, 'Top50Service'), \
            "Top50Service should not be exported from app.services.nba"


class TestParlayServiceNoTop50:
    """Test that ParlayService works without top_50_player_ids parameter."""

    def test_parlay_service_init_without_top_50(self, db_session: Session):
        """Verify ParlayService can be instantiated without any top_50 dependencies."""
        from app.services.core.parlay_service import ParlayService

        # Should be able to instantiate with just db session
        service = ParlayService(db_session)
        assert service is not None
        assert service.db == db_session

    def test_parlay_service_methods_dont_accept_top_50(self, db_session: Session):
        """Verify ParlayService methods don't accept top_50_player_ids parameter."""
        from app.services.core.parlay_service import ParlayService
        import inspect

        service = ParlayService(db_session)

        # Check key methods don't have top_50_player_ids parameter
        methods_to_check = [
            'generate_same_game_parlays',
            'generate_same_game_parlays_optimized',
            'generate_cross_game_parlays',
            'generate_combo_parlays'
        ]

        for method_name in methods_to_check:
            if hasattr(service, method_name):
                method = getattr(service, method_name)
                sig = inspect.signature(method)
                params = list(sig.parameters.keys())

                assert 'top_50_player_ids' not in params, \
                    f"{method_name} should not accept top_50_player_ids parameter"


class TestDatabaseTableRemoval:
    """Test that top_50_players table does not exist in the database."""

    def test_top_50_players_table_not_in_models(self, db_session: Session):
        """Verify Top50Players model does not exist in app.models.nba.models."""
        from app.models.nba import models

        # Check that Top50Players class doesn't exist
        assert not hasattr(models, 'Top50Players'), \
            "Top50Players model should not exist in app.models.nba.models"

    def test_top_50_players_table_not_in_database(self, db_session: Session):
        """Verify top_50_players table does not exist in database schema."""
        inspector = inspect(db_session.bind)
        tables = inspector.get_table_names()

        assert 'top_50_players' not in tables, \
            f"top_50_players table should not exist. Found tables: {tables}"

    def test_cannot_query_top_50_players(self, db_session: Session):
        """Verify that attempting to query top_50_players raises an error."""
        from sqlalchemy import text

        with pytest.raises(Exception) as exc_info:
            db_session.execute(text("SELECT * FROM top_50_players"))

        # Should be a table doesn't exist error
        assert "does not exist" in str(exc_info.value).lower() or \
               "no such table" in str(exc_info.value).lower() or \
               "relation" in str(exc_info.value).lower()


class TestScriptExecution:
    """Test that generate_smart_parlays.py runs without Top 50 dependencies."""

    def test_generate_smart_parlays_imports_without_top_50(self):
        """Verify generate_smart_parlays.py can be imported without Top50Service."""
        script_path = PROJECT_ROOT / "scripts" / "generate_smart_parlays.py"

        assert script_path.exists(), \
            f"generate_smart_parlays.py not found at {script_path}"

        # Read the script and check it doesn't import Top50Service
        content = script_path.read_text()

        assert "from app.services.nba.top_50_service" not in content, \
            "generate_smart_parlays.py should not import Top50Service"
        assert "import Top50Service" not in content, \
            "generate_smart_parlays.py should not import Top50Service"

    def test_generate_smart_parlays_no_top_50_logic(self):
        """Verify generate_smart_parlays.py doesn't use top_50 filtering logic."""
        script_path = PROJECT_ROOT / "scripts" / "generate_smart_parlays.py"
        content = script_path.read_text()

        # Check for old top_50 patterns (excluding comments)
        lines = content.split('\n')
        code_lines = [
            line for line in lines
            if not line.strip().startswith('#')
        ]

        code = '\n'.join(code_lines)

        # These patterns should not appear in actual code (only in comments is OK)
        assert "top_50_player_ids" not in code or code.count("top_50_player_ids") == 0, \
            "generate_smart_parlays.py should not reference top_50_player_ids in code"

    def test_generate_smart_parlays_uses_injury_filtering(self):
        """Verify generate_smart_parlays.py uses injury filtering instead of top_50."""
        script_path = PROJECT_ROOT / "scripts" / "generate_smart_parlays.py"
        content = script_path.read_text()

        # Should use InjuryService for filtering
        assert "InjuryService" in content, \
            "generate_smart_parlays.py should use InjuryService for filtering"

        # Should filter by injury status
        assert "filter_by_injury_status" in content, \
            "generate_smart_parlays.py should use filter_by_injury_status"

        # Should mention healthy/active players
        assert "healthy" in content.lower() or "active" in content.lower(), \
            "generate_smart_parlays.py should reference healthy/active players"


class TestNoTop50ReferencesInKeyFiles:
    """Test that key files don't have references to top_50 (except in comments/migrations)."""

    @pytest.mark.parametrize("file_path", [
        "app/services/core/parlay_service.py",
        "app/services/nba/prediction_service.py",
        "app/services/nba/injury_service.py",
        "app/api/routes/parlays.py",
        "app/main.py",
    ])
    def test_no_top_50_references_in_file(self, file_path):
        """Verify specified files don't have top_50 references in code (only comments allowed)."""
        full_path = PROJECT_ROOT / file_path

        if not full_path.exists():
            pytest.skip(f"File {file_path} does not exist")

        content = full_path.read_text()

        # Split into lines and check code (not comments)
        lines = content.split('\n')
        code_lines = [
            line for line in lines
            if not line.strip().startswith('#')
            and 'top_50' in line.lower()
        ]

        # Filter out comment-only lines more thoroughly
        actual_code_with_top_50 = []
        for line in code_lines:
            stripped = line.strip()
            # Skip if it's just a comment
            if stripped.startswith('#'):
                continue
            # Skip if it's in a multi-line string (docstring)
            if '"""' in line or "'''" in line:
                continue
            actual_code_with_top_50.append(line)

        # Should not have any top_50 references in actual code
        assert len(actual_code_with_top_50) == 0, \
            f"{file_path} should not have top_50 references in code. Found: {actual_code_with_top_50}"

    def test_migration_file_exists_for_removal(self):
        """Verify migration file 015_drop_top_50_players.sql exists."""
        migration_path = PROJECT_ROOT / "migrations" / "015_drop_top_50_players.sql"

        assert migration_path.exists(), \
            f"Migration file should exist at {migration_path}"

        content = migration_path.read_text()

        # Should drop the table
        assert "DROP TABLE" in content.upper(), \
            "Migration should contain DROP TABLE statement"

        assert "top_50_players" in content.lower(), \
            "Migration should reference top_50_players table"


class TestTop50ScriptRemoval:
    """Test that Top 50 related scripts have been removed."""

    def test_refresh_top_50_weekly_script_removed(self):
        """Verify refresh_top_50_weekly.py script has been removed."""
        script_path = PROJECT_ROOT / "scripts" / "refresh_top_50_weekly.py"

        assert not script_path.exists(), \
            f"refresh_top_50_weekly.py should be removed from {script_path}"

    def test_no_top_50_scripts_in_scripts_dir(self):
        """Verify no top_50 related scripts exist in scripts directory."""
        scripts_dir = PROJECT_ROOT / "scripts"

        if not scripts_dir.exists():
            pytest.skip("scripts directory does not exist")

        # Find all Python files
        py_files = list(scripts_dir.glob("*.py"))

        # Check none have top_50 in the name
        top_50_files = [
            f for f in py_files
            if 'top_50' in f.name.lower() or 'top50' in f.name.lower()
        ]

        assert len(top_50_files) == 0, \
            f"Found top_50 related scripts that should be removed: {top_50_files}"


class TestTop50ServiceNotInScheduler:
    """Test that Top50Service is not referenced in the scheduler."""

    def test_scheduler_no_top_50_reference(self):
        """Verify scheduler.py doesn't reference Top50Service."""
        scheduler_path = PROJECT_ROOT / "app" / "core" / "scheduler.py"

        if not scheduler_path.exists():
            pytest.skip("scheduler.py does not exist")

        content = scheduler_path.read_text()

        # Should not import Top50Service
        assert "top_50_service" not in content.lower(), \
            "scheduler.py should not reference top_50_service"


class TestParlayGenerationWithoutTop50:
    """Integration tests for parlay generation without Top 50."""

    def test_parlay_service_works_with_injury_filtering(
        self,
        db_session: Session,
        sample_games
    ):
        """Verify ParlayService works when using injury filtering instead of top_50."""
        from app.services.core.parlay_service import ParlayService
        from app.models.nba.models import Player, Prediction, PlayerInjury
        from datetime import datetime
        import uuid

        # Create test players
        player1 = Player(
            id=str(uuid.uuid4()),
            external_id="test_player_1",
            id_source="test",
            name="Test Player 1",
            team="BOS",
            position="PG",
            active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        player2 = Player(
            id=str(uuid.uuid4()),
            external_id="test_player_2",
            id_source="test",
            name="Test Player 2",
            team="PHI",
            position="SG",
            active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db_session.add_all([player1, player2])
        db_session.commit()

        # Create predictions for these players
        game = sample_games[0]

        pred1 = Prediction(
            id=str(uuid.uuid4()),
            game_id=str(game.id),
            player_id=str(player1.id),
            stat_type="points",
            predicted_value=25.5,
            bookmaker_line=24.5,
            recommendation="OVER",
            confidence=0.75,
            over_price=-110,
            under_price=-110,
            created_at=datetime.utcnow()
        )

        pred2 = Prediction(
            id=str(uuid.uuid4()),
            game_id=str(game.id),
            player_id=str(player2.id),
            stat_type="points",
            predicted_value=22.5,
            bookmaker_line=21.5,
            recommendation="OVER",
            confidence=0.70,
            over_price=-110,
            under_price=-110,
            created_at=datetime.utcnow()
        )

        db_session.add_all([pred1, pred2])
        db_session.commit()

        # Create ParlayService and verify it works
        service = ParlayService(db_session)

        # Should be able to generate parlays without top_50_player_ids
        # (might return empty list due to test data, but shouldn't error)
        try:
            parlays = service.generate_same_game_parlays_optimized(
                game_id=str(game.id),
                min_confidence=0.60,
                max_legs=2,
                min_ev=-0.20
            )
            # Success - no error means it works without top_50
            assert isinstance(parlays, list)
        except Exception as e:
            pytest.fail(f"ParlayService should work without top_50_player_ids. Error: {e}")


class TestMigrationApplied:
    """Test that the migration to drop top_50_players has been applied."""

    def test_migration_file_exists(self):
        """Verify migration 015_drop_top_50_players.sql exists."""
        migration_path = PROJECT_ROOT / "migrations" / "015_drop_top_50_players.sql"

        assert migration_path.exists(), \
            "Migration file 015_drop_top_50_players.sql should exist"

    def test_migration_content_correct(self):
        """Verify migration file has correct DROP TABLE statement."""
        migration_path = PROJECT_ROOT / "migrations" / "015_drop_top_50_players.sql"
        content = migration_path.read_text()

        # Should have DROP TABLE IF EXISTS with CASCADE
        assert "DROP TABLE IF EXISTS top_50_players" in content, \
            "Migration should have DROP TABLE IF EXISTS top_50_players"

        # Should use CASCADE to handle foreign keys
        assert "CASCADE" in content.upper(), \
            "Migration should use CASCADE to handle dependencies"

    def test_migration_listed_in_run_migrations(self):
        """Verify migration is listed in run_migrations.py."""
        migrations_script = PROJECT_ROOT / "scripts" / "run_migrations.py"

        if not migrations_script.exists():
            pytest.skip("run_migrations.py does not exist")

        content = migrations_script.read_text()

        # Should reference the migration file
        assert "015_drop_top_50_players.sql" in content, \
            "run_migrations.py should include 015_drop_top_50_players.sql"
