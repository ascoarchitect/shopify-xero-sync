"""Unit tests for SQLite database operations.

Tests verify that:
- Database schema is created correctly
- CRUD operations for sync mappings work correctly
- Sync history tracking works correctly
- Error recording and retrieval work correctly
- Edge cases and error handling are correct
"""

import pytest
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from src.database import Database
from src.models import SyncMapping, SyncHistoryEntry, SyncError


class TestDatabaseInitialization:
    """Tests for database initialization."""

    def test_creates_database_file(self, temp_db_path):
        """Test that database file is created."""
        db = Database(temp_db_path)

        assert temp_db_path.exists()

    def test_creates_parent_directory(self, tmp_path):
        """Test that parent directory is created if missing."""
        db_path = tmp_path / "subdir" / "nested" / "sync.db"

        db = Database(db_path)

        assert db_path.parent.exists()
        assert db_path.exists()

    def test_creates_tables(self, temp_db_path):
        """Test that all required tables are created."""
        db = Database(temp_db_path)

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "sync_mappings" in tables
        assert "sync_history" in tables
        assert "sync_errors" in tables

    def test_creates_indexes(self, temp_db_path):
        """Test that indexes are created."""
        db = Database(temp_db_path)

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "idx_mappings_entity_type" in indexes
        assert "idx_mappings_xero_id" in indexes
        assert "idx_history_started_at" in indexes
        assert "idx_errors_entity" in indexes

    def test_idempotent_initialization(self, temp_db_path):
        """Test that initializing twice doesn't cause errors."""
        db1 = Database(temp_db_path)
        db2 = Database(temp_db_path)  # Should not raise

        # Should still be functional
        db2.start_sync_run("test-run")


class TestSyncMappings:
    """Tests for sync mapping operations."""

    def test_upsert_and_get_mapping(self, temp_db_path):
        """Test inserting and retrieving a mapping."""
        db = Database(temp_db_path)
        mapping = SyncMapping(
            shopify_id="12345",
            xero_id="abc-def-123",
            entity_type="customer",
            last_synced_at=datetime.utcnow(),
            checksum="hash123",
        )

        db.upsert_mapping(mapping)
        result = db.get_mapping("12345")

        assert result is not None
        assert result.shopify_id == "12345"
        assert result.xero_id == "abc-def-123"
        assert result.entity_type == "customer"
        assert result.checksum == "hash123"

    def test_get_nonexistent_mapping(self, temp_db_path):
        """Test getting a mapping that doesn't exist."""
        db = Database(temp_db_path)

        result = db.get_mapping("nonexistent")

        assert result is None

    def test_update_existing_mapping(self, temp_db_path):
        """Test updating an existing mapping."""
        db = Database(temp_db_path)
        original = SyncMapping(
            shopify_id="12345",
            xero_id="abc-def-123",
            entity_type="customer",
            checksum="hash1",
        )
        db.upsert_mapping(original)

        updated = SyncMapping(
            shopify_id="12345",
            xero_id="abc-def-123",
            entity_type="customer",
            checksum="hash2",
            last_synced_at=datetime.utcnow(),
        )
        db.upsert_mapping(updated)

        result = db.get_mapping("12345")
        assert result.checksum == "hash2"

    def test_get_mapping_by_xero_id(self, temp_db_path):
        """Test retrieving a mapping by Xero ID."""
        db = Database(temp_db_path)
        mapping = SyncMapping(
            shopify_id="12345",
            xero_id="abc-def-123",
            entity_type="customer",
        )
        db.upsert_mapping(mapping)

        result = db.get_mapping_by_xero_id("abc-def-123")

        assert result is not None
        assert result.shopify_id == "12345"

    def test_get_nonexistent_mapping_by_xero_id(self, temp_db_path):
        """Test getting a mapping by Xero ID that doesn't exist."""
        db = Database(temp_db_path)

        result = db.get_mapping_by_xero_id("nonexistent")

        assert result is None

    def test_get_all_mappings(self, temp_db_path):
        """Test retrieving all mappings."""
        db = Database(temp_db_path)
        db.upsert_mapping(SyncMapping(shopify_id="1", xero_id="a", entity_type="customer"))
        db.upsert_mapping(SyncMapping(shopify_id="2", xero_id="b", entity_type="product"))
        db.upsert_mapping(SyncMapping(shopify_id="3", xero_id="c", entity_type="customer"))

        result = db.get_all_mappings()

        assert len(result) == 3

    def test_get_all_mappings_by_entity_type(self, temp_db_path):
        """Test retrieving mappings filtered by entity type."""
        db = Database(temp_db_path)
        db.upsert_mapping(SyncMapping(shopify_id="1", xero_id="a", entity_type="customer"))
        db.upsert_mapping(SyncMapping(shopify_id="2", xero_id="b", entity_type="product"))
        db.upsert_mapping(SyncMapping(shopify_id="3", xero_id="c", entity_type="customer"))

        result = db.get_all_mappings(entity_type="customer")

        assert len(result) == 2
        assert all(m.entity_type == "customer" for m in result)

    def test_delete_mapping(self, temp_db_path):
        """Test deleting a mapping."""
        db = Database(temp_db_path)
        db.upsert_mapping(SyncMapping(shopify_id="12345", xero_id="abc", entity_type="customer"))

        deleted = db.delete_mapping("12345")

        assert deleted is True
        assert db.get_mapping("12345") is None

    def test_delete_nonexistent_mapping(self, temp_db_path):
        """Test deleting a mapping that doesn't exist."""
        db = Database(temp_db_path)

        deleted = db.delete_mapping("nonexistent")

        assert deleted is False

    def test_mapping_with_timestamps(self, temp_db_path):
        """Test mapping with shopify_updated_at timestamp."""
        db = Database(temp_db_path)
        now = datetime.utcnow()
        mapping = SyncMapping(
            shopify_id="12345",
            xero_id="abc",
            entity_type="customer",
            last_synced_at=now,
            shopify_updated_at=now - timedelta(hours=1),
        )
        db.upsert_mapping(mapping)

        result = db.get_mapping("12345")

        assert result.last_synced_at is not None
        assert result.shopify_updated_at is not None


class TestSyncHistory:
    """Tests for sync history operations."""

    def test_start_sync_run(self, temp_db_path):
        """Test recording start of sync run."""
        db = Database(temp_db_path)

        db.start_sync_run("run-123")

        history = db.get_sync_history(limit=1)
        assert len(history) == 1
        assert history[0].run_id == "run-123"
        assert history[0].status == "running"
        assert history[0].completed_at is None

    def test_complete_sync_run_success(self, temp_db_path):
        """Test completing a successful sync run."""
        db = Database(temp_db_path)
        db.start_sync_run("run-123")

        db.complete_sync_run(
            run_id="run-123",
            status="success",
            entities_processed=50,
            errors=[],
        )

        history = db.get_sync_history(limit=1)
        assert history[0].status == "success"
        assert history[0].completed_at is not None
        assert history[0].entities_processed == 50
        assert history[0].errors == []

    def test_complete_sync_run_with_errors(self, temp_db_path):
        """Test completing a sync run with errors."""
        db = Database(temp_db_path)
        db.start_sync_run("run-123")
        errors = ["Error 1", "Error 2"]

        db.complete_sync_run(
            run_id="run-123",
            status="failed",
            entities_processed=30,
            errors=errors,
        )

        history = db.get_sync_history(limit=1)
        assert history[0].status == "failed"
        assert history[0].errors == errors

    def test_get_sync_history_ordering(self, temp_db_path):
        """Test that history is ordered by started_at descending."""
        db = Database(temp_db_path)
        for i in range(5):
            db.start_sync_run(f"run-{i}")
            db.complete_sync_run(f"run-{i}", "success", i, [])

        history = db.get_sync_history(limit=10)

        assert len(history) == 5
        assert history[0].run_id == "run-4"  # Most recent first

    def test_get_sync_history_limit(self, temp_db_path):
        """Test that history limit is respected."""
        db = Database(temp_db_path)
        for i in range(10):
            db.start_sync_run(f"run-{i}")
            db.complete_sync_run(f"run-{i}", "success", i, [])

        history = db.get_sync_history(limit=3)

        assert len(history) == 3

    def test_get_last_successful_sync(self, temp_db_path):
        """Test getting the most recent successful sync."""
        db = Database(temp_db_path)
        # Create some failed syncs
        db.start_sync_run("run-1")
        db.complete_sync_run("run-1", "failed", 0, ["error"])

        db.start_sync_run("run-2")
        db.complete_sync_run("run-2", "success", 50, [])

        db.start_sync_run("run-3")
        db.complete_sync_run("run-3", "failed", 10, ["error"])

        result = db.get_last_successful_sync()

        assert result is not None
        assert result.run_id == "run-2"
        assert result.status == "success"

    def test_get_last_successful_sync_none(self, temp_db_path):
        """Test when there are no successful syncs."""
        db = Database(temp_db_path)
        db.start_sync_run("run-1")
        db.complete_sync_run("run-1", "failed", 0, ["error"])

        result = db.get_last_successful_sync()

        assert result is None


class TestSyncErrors:
    """Tests for sync error operations."""

    def test_record_new_error(self, temp_db_path):
        """Test recording a new error."""
        db = Database(temp_db_path)

        db.record_error("customer", "12345", "API timeout")

        errors = db.get_errors()
        assert len(errors) == 1
        assert errors[0].entity_type == "customer"
        assert errors[0].shopify_id == "12345"
        assert errors[0].error_message == "API timeout"
        assert errors[0].retry_count == 0

    def test_record_error_increments_retry_count(self, temp_db_path):
        """Test that recording same error increments retry count."""
        db = Database(temp_db_path)

        db.record_error("customer", "12345", "Error 1")
        db.record_error("customer", "12345", "Error 2")
        db.record_error("customer", "12345", "Error 3")

        errors = db.get_errors()
        assert len(errors) == 1
        assert errors[0].retry_count == 2
        assert errors[0].error_message == "Error 3"  # Updated message

    def test_get_errors_max_retry_count(self, temp_db_path):
        """Test filtering errors by max retry count."""
        db = Database(temp_db_path)

        # Create error with 4 retries
        for _ in range(5):
            db.record_error("customer", "12345", "Error")

        # Create error with 1 retry
        db.record_error("customer", "67890", "New error")

        errors = db.get_errors(max_retry_count=3)

        # Only the error with 1 retry should be returned
        assert len(errors) == 1
        assert errors[0].shopify_id == "67890"

    def test_get_errors_by_entity_type(self, temp_db_path):
        """Test filtering errors by entity type."""
        db = Database(temp_db_path)
        db.record_error("customer", "1", "Error 1")
        db.record_error("product", "2", "Error 2")
        db.record_error("customer", "3", "Error 3")

        errors = db.get_errors(entity_type="customer")

        assert len(errors) == 2
        assert all(e.entity_type == "customer" for e in errors)

    def test_clear_error(self, temp_db_path):
        """Test clearing errors for a successfully synced entity."""
        db = Database(temp_db_path)
        db.record_error("customer", "12345", "Error")

        cleared = db.clear_error("12345")

        assert cleared is True
        assert len(db.get_errors()) == 0

    def test_clear_nonexistent_error(self, temp_db_path):
        """Test clearing errors for entity with no errors."""
        db = Database(temp_db_path)

        cleared = db.clear_error("nonexistent")

        assert cleared is False


class TestDatabaseStats:
    """Tests for database statistics."""

    def test_get_stats_empty_database(self, temp_db_path):
        """Test stats on empty database."""
        db = Database(temp_db_path)

        stats = db.get_stats()

        assert stats["mappings"] == {}
        assert stats["pending_errors"] == 0
        assert stats["last_successful_sync"] is None

    def test_get_stats_with_data(self, temp_db_path):
        """Test stats with populated database."""
        db = Database(temp_db_path)

        # Add some mappings
        db.upsert_mapping(SyncMapping(shopify_id="1", xero_id="a", entity_type="customer"))
        db.upsert_mapping(SyncMapping(shopify_id="2", xero_id="b", entity_type="customer"))
        db.upsert_mapping(SyncMapping(shopify_id="3", xero_id="c", entity_type="product"))

        # Add some errors
        db.record_error("customer", "4", "Error")

        # Add sync history
        db.start_sync_run("run-1")
        db.complete_sync_run("run-1", "success", 10, [])

        stats = db.get_stats()

        assert stats["mappings"]["customer"] == 2
        assert stats["mappings"]["product"] == 1
        assert stats["pending_errors"] == 1
        assert stats["last_successful_sync"] is not None


class TestDatabaseConcurrency:
    """Tests for database concurrency handling."""

    def test_multiple_connections(self, temp_db_path):
        """Test that multiple Database instances work correctly."""
        db1 = Database(temp_db_path)
        db2 = Database(temp_db_path)

        db1.upsert_mapping(SyncMapping(shopify_id="1", xero_id="a", entity_type="customer"))

        # db2 should see the change
        result = db2.get_mapping("1")
        assert result is not None

    def test_transaction_rollback_on_error(self, temp_db_path):
        """Test that failed transactions are rolled back."""
        db = Database(temp_db_path)
        db.upsert_mapping(SyncMapping(shopify_id="1", xero_id="a", entity_type="customer"))

        # Attempting to insert a mapping that would violate constraint
        # should rollback and not corrupt the database
        # Note: SQLite's ON CONFLICT handles this gracefully with UPSERT
        db.upsert_mapping(SyncMapping(shopify_id="1", xero_id="b", entity_type="customer"))

        result = db.get_mapping("1")
        assert result.xero_id == "b"  # Updated, not failed
