"""SQLite database operations for sync state management.

The database is a disposable cache - it can be rebuilt from the APIs.
It tracks mappings between Shopify and Xero entities to prevent duplicates
and detect changes via checksums.
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from contextlib import contextmanager

from .models import SyncMapping, SyncHistoryEntry, SyncError

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager for sync state."""

    SCHEMA = """
    -- Track entity mappings between Shopify and Xero
    CREATE TABLE IF NOT EXISTS sync_mappings (
        shopify_id TEXT PRIMARY KEY,
        xero_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        last_synced_at TIMESTAMP,
        shopify_updated_at TIMESTAMP,
        checksum TEXT
    );

    -- Index for efficient lookups by entity type
    CREATE INDEX IF NOT EXISTS idx_mappings_entity_type
    ON sync_mappings(entity_type);

    -- Index for lookups by xero_id (for reverse mapping)
    CREATE INDEX IF NOT EXISTS idx_mappings_xero_id
    ON sync_mappings(xero_id);

    -- Track sync run history for auditing
    CREATE TABLE IF NOT EXISTS sync_history (
        run_id TEXT PRIMARY KEY,
        started_at TIMESTAMP NOT NULL,
        completed_at TIMESTAMP,
        status TEXT NOT NULL,
        entities_processed INTEGER DEFAULT 0,
        errors TEXT
    );

    -- Index for efficient history queries
    CREATE INDEX IF NOT EXISTS idx_history_started_at
    ON sync_history(started_at DESC);

    -- Track errors for retry
    CREATE TABLE IF NOT EXISTS sync_errors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        shopify_id TEXT NOT NULL,
        error_message TEXT NOT NULL,
        occurred_at TIMESTAMP NOT NULL,
        retry_count INTEGER DEFAULT 0
    );

    -- Index for finding retryable errors
    CREATE INDEX IF NOT EXISTS idx_errors_entity
    ON sync_errors(entity_type, shopify_id);
    """

    def __init__(self, db_path: Path):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_directory()
        self._init_schema()

    def _ensure_directory(self) -> None:
        """Ensure the database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _init_schema(self) -> None:
        """Initialize database schema if not exists."""
        with self._get_connection() as conn:
            conn.executescript(self.SCHEMA)
            logger.info(f"Database initialized at {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper settings.

        Yields:
            sqlite3.Connection: Database connection
        """
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0  # Wait up to 30 seconds for locks to clear
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # =========================================================================
    # SYNC MAPPINGS
    # =========================================================================

    def get_mapping(self, shopify_id: str) -> Optional[SyncMapping]:
        """Get mapping for a Shopify entity.

        Args:
            shopify_id: Shopify entity ID

        Returns:
            SyncMapping or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sync_mappings WHERE shopify_id = ?",
                (shopify_id,)
            )
            row = cursor.fetchone()
            if row:
                return SyncMapping(
                    shopify_id=row["shopify_id"],
                    xero_id=row["xero_id"],
                    entity_type=row["entity_type"],
                    last_synced_at=row["last_synced_at"],
                    shopify_updated_at=row["shopify_updated_at"],
                    checksum=row["checksum"],
                )
            return None

    def get_mapping_by_xero_id(self, xero_id: str) -> Optional[SyncMapping]:
        """Get mapping by Xero entity ID.

        Args:
            xero_id: Xero entity ID

        Returns:
            SyncMapping or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sync_mappings WHERE xero_id = ?",
                (xero_id,)
            )
            row = cursor.fetchone()
            if row:
                return SyncMapping(
                    shopify_id=row["shopify_id"],
                    xero_id=row["xero_id"],
                    entity_type=row["entity_type"],
                    last_synced_at=row["last_synced_at"],
                    shopify_updated_at=row["shopify_updated_at"],
                    checksum=row["checksum"],
                )
            return None

    def get_all_mappings(self, entity_type: Optional[str] = None) -> List[SyncMapping]:
        """Get all mappings, optionally filtered by entity type.

        Args:
            entity_type: Filter by entity type (customer, product, order)

        Returns:
            List of SyncMapping objects
        """
        with self._get_connection() as conn:
            if entity_type:
                cursor = conn.execute(
                    "SELECT * FROM sync_mappings WHERE entity_type = ?",
                    (entity_type,)
                )
            else:
                cursor = conn.execute("SELECT * FROM sync_mappings")

            return [
                SyncMapping(
                    shopify_id=row["shopify_id"],
                    xero_id=row["xero_id"],
                    entity_type=row["entity_type"],
                    last_synced_at=row["last_synced_at"],
                    shopify_updated_at=row["shopify_updated_at"],
                    checksum=row["checksum"],
                )
                for row in cursor.fetchall()
            ]

    def upsert_mapping(self, mapping: SyncMapping) -> None:
        """Insert or update a sync mapping.

        Args:
            mapping: SyncMapping to save
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sync_mappings
                    (shopify_id, xero_id, entity_type, last_synced_at, shopify_updated_at, checksum)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(shopify_id) DO UPDATE SET
                    xero_id = excluded.xero_id,
                    last_synced_at = excluded.last_synced_at,
                    shopify_updated_at = excluded.shopify_updated_at,
                    checksum = excluded.checksum
                """,
                (
                    mapping.shopify_id,
                    mapping.xero_id,
                    mapping.entity_type,
                    mapping.last_synced_at,
                    mapping.shopify_updated_at,
                    mapping.checksum,
                )
            )
            logger.debug(f"Upserted mapping: {mapping.shopify_id} -> {mapping.xero_id}")

    def delete_mapping(self, shopify_id: str) -> bool:
        """Delete a sync mapping.

        Args:
            shopify_id: Shopify entity ID to delete

        Returns:
            True if deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sync_mappings WHERE shopify_id = ?",
                (shopify_id,)
            )
            return cursor.rowcount > 0

    # =========================================================================
    # SYNC HISTORY
    # =========================================================================

    def start_sync_run(self, run_id: str) -> None:
        """Record the start of a sync run.

        Args:
            run_id: Unique ID for this sync run
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sync_history (run_id, started_at, status, entities_processed, errors)
                VALUES (?, ?, 'running', 0, '[]')
                """,
                (run_id, datetime.utcnow())
            )
            logger.info(f"Started sync run: {run_id}")

    def complete_sync_run(
        self,
        run_id: str,
        status: str,
        entities_processed: int,
        errors: List[str]
    ) -> None:
        """Record completion of a sync run.

        Args:
            run_id: Sync run ID
            status: Final status (success, failed)
            entities_processed: Number of entities processed
            errors: List of error messages
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE sync_history
                SET completed_at = ?,
                    status = ?,
                    entities_processed = ?,
                    errors = ?
                WHERE run_id = ?
                """,
                (datetime.utcnow(), status, entities_processed, json.dumps(errors), run_id)
            )
            logger.info(f"Completed sync run: {run_id} with status {status}")

    def get_sync_history(self, limit: int = 10) -> List[SyncHistoryEntry]:
        """Get recent sync history.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of SyncHistoryEntry objects
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sync_history ORDER BY started_at DESC LIMIT ?",
                (limit,)
            )
            return [
                SyncHistoryEntry(
                    run_id=row["run_id"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    status=row["status"],
                    entities_processed=row["entities_processed"],
                    errors=json.loads(row["errors"]) if row["errors"] else [],
                )
                for row in cursor.fetchall()
            ]

    def get_last_successful_sync(self) -> Optional[SyncHistoryEntry]:
        """Get the most recent successful sync run.

        Returns:
            SyncHistoryEntry or None if no successful syncs
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM sync_history
                WHERE status = 'success'
                ORDER BY completed_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row:
                return SyncHistoryEntry(
                    run_id=row["run_id"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    status=row["status"],
                    entities_processed=row["entities_processed"],
                    errors=json.loads(row["errors"]) if row["errors"] else [],
                )
            return None

    # =========================================================================
    # SYNC ERRORS
    # =========================================================================

    def record_error(
        self,
        entity_type: str,
        shopify_id: str,
        error_message: str
    ) -> None:
        """Record a sync error for later retry.

        Args:
            entity_type: Type of entity (customer, product, order)
            shopify_id: Shopify entity ID that failed
            error_message: Error message
        """
        with self._get_connection() as conn:
            # Check if error already exists for this entity
            cursor = conn.execute(
                """
                SELECT id, retry_count FROM sync_errors
                WHERE entity_type = ? AND shopify_id = ?
                ORDER BY occurred_at DESC LIMIT 1
                """,
                (entity_type, shopify_id)
            )
            existing = cursor.fetchone()

            if existing:
                # Update retry count
                conn.execute(
                    """
                    UPDATE sync_errors
                    SET error_message = ?, occurred_at = ?, retry_count = retry_count + 1
                    WHERE id = ?
                    """,
                    (error_message, datetime.utcnow(), existing["id"])
                )
            else:
                # Insert new error
                conn.execute(
                    """
                    INSERT INTO sync_errors (entity_type, shopify_id, error_message, occurred_at, retry_count)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (entity_type, shopify_id, error_message, datetime.utcnow())
                )

            logger.warning(f"Recorded error for {entity_type} {shopify_id}: {error_message}")

    def get_errors(
        self,
        entity_type: Optional[str] = None,
        max_retry_count: int = 3
    ) -> List[SyncError]:
        """Get errors eligible for retry.

        Args:
            entity_type: Filter by entity type
            max_retry_count: Only return errors with fewer retries

        Returns:
            List of SyncError objects
        """
        with self._get_connection() as conn:
            if entity_type:
                cursor = conn.execute(
                    """
                    SELECT * FROM sync_errors
                    WHERE entity_type = ? AND retry_count < ?
                    ORDER BY occurred_at DESC
                    """,
                    (entity_type, max_retry_count)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM sync_errors
                    WHERE retry_count < ?
                    ORDER BY occurred_at DESC
                    """,
                    (max_retry_count,)
                )

            return [
                SyncError(
                    id=row["id"],
                    entity_type=row["entity_type"],
                    shopify_id=row["shopify_id"],
                    error_message=row["error_message"],
                    occurred_at=row["occurred_at"],
                    retry_count=row["retry_count"],
                )
                for row in cursor.fetchall()
            ]

    def clear_error(self, shopify_id: str) -> bool:
        """Clear errors for a successfully synced entity.

        Args:
            shopify_id: Shopify entity ID

        Returns:
            True if errors were cleared
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sync_errors WHERE shopify_id = ?",
                (shopify_id,)
            )
            if cursor.rowcount > 0:
                logger.debug(f"Cleared errors for {shopify_id}")
                return True
            return False

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_stats(self) -> dict:
        """Get database statistics.

        Returns:
            Dictionary with counts and statistics
        """
        with self._get_connection() as conn:
            stats = {}

            # Count mappings by type
            cursor = conn.execute(
                "SELECT entity_type, COUNT(*) as count FROM sync_mappings GROUP BY entity_type"
            )
            stats["mappings"] = {row["entity_type"]: row["count"] for row in cursor.fetchall()}

            # Count pending errors
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM sync_errors WHERE retry_count < 3"
            )
            stats["pending_errors"] = cursor.fetchone()["count"]

            # Last sync info
            last_sync = self.get_last_successful_sync()
            if last_sync:
                stats["last_successful_sync"] = last_sync.completed_at.isoformat() if last_sync.completed_at else None
            else:
                stats["last_successful_sync"] = None

            return stats
