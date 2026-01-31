"""
Helper utilities for database migrations.

Provides common functionality used across migrations like batch processing,
session management, and progress reporting.
"""

import logging
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from sqlalchemy.orm import Session

from models.database import Base

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Base)


class MigrationHelper:
    """Helper class for database migrations"""

    def __init__(self, session: Session):
        """
        Initialize migration helper

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    def batch_process(
        self,
        model_class: Type[T],
        process_func: Callable[[T], bool],
        batch_size: int = 100,
        filter_condition: Optional[Any] = None,
    ) -> Dict[str, int]:
        """
        Process all records of a model in batches

        Args:
            model_class: SQLAlchemy model class to process
            process_func: Function to process each record. Should return True if record was modified.
            batch_size: Number of records to process per batch
            filter_condition: Optional SQLAlchemy filter condition

        Returns:
            Dictionary with 'processed', 'modified', 'skipped' counts

        Example:
            >>> def migrate_record(record):
            ...     if record.needs_migration:
            ...         record.new_field = transform(record.old_field)
            ...         return True
            ...     return False
            >>> helper = MigrationHelper(session)
            >>> stats = helper.batch_process(MyModel, migrate_record)
            >>> print(f"Modified {stats['modified']} records")
        """
        # Get total count
        query = self.session.query(model_class)
        if filter_condition is not None:
            query = query.filter(filter_condition)

        total_count = query.count()
        logger.info(f"Found {total_count} {model_class.__name__} records to process")

        processed_count = 0
        modified_count = 0
        skipped_count = 0

        # Process in batches
        for offset in range(0, total_count, batch_size):
            query = self.session.query(model_class)
            if filter_condition is not None:
                query = query.filter(filter_condition)

            records = query.offset(offset).limit(batch_size).all()

            for record in records:
                try:
                    if process_func(record):
                        modified_count += 1
                    else:
                        skipped_count += 1
                    processed_count += 1
                except Exception as e:
                    logger.error(f"Error processing {model_class.__name__} record {record.id}: {e}")
                    skipped_count += 1

            # Commit batch
            self.session.commit()
            logger.info(f"Processed {offset + len(records)}/{total_count} {model_class.__name__} records...")

        return {
            "total": total_count,
            "processed": processed_count,
            "modified": modified_count,
            "skipped": skipped_count,
        }

    def show_sample(
        self,
        model_class: Type[T],
        field_names: Optional[list[str]] = None,
        limit: int = 1,
    ) -> None:
        """
        Display sample records after migration

        Args:
            model_class: SQLAlchemy model class
            field_names: List of field names to display (None = show all)
            limit: Number of samples to show
        """
        samples = self.session.query(model_class).limit(limit).all()

        for i, sample in enumerate(samples, 1):
            logger.info(f"\n📋 Sample {i} (ID {sample.id}):")

            if field_names is None:
                # Show all fields from to_dict if available
                if hasattr(sample, "to_dict"):
                    data = sample.to_dict()
                    for key, value in data.items():
                        logger.info(f"   {key}: {value}")
                else:
                    # Show __dict__ excluding private fields
                    for key, value in sample.__dict__.items():
                        if not key.startswith("_"):
                            logger.info(f"   {key}: {value}")
            else:
                # Show specific fields
                for field in field_names:
                    value = getattr(sample, field, None)
                    if isinstance(value, dict):
                        logger.info(f"   {field} keys: {list(value.keys()) if value else 'None'}")
                    else:
                        logger.info(f"   {field}: {value}")

    @staticmethod
    def print_stats(migration_name: str, stats: Dict[str, int]) -> None:
        """
        Print migration statistics

        Args:
            migration_name: Name of the migration
            stats: Statistics dictionary from batch_process
        """
        print(f"\n✅ {migration_name} complete!")
        print(f"   Total records: {stats['total']}")
        print(f"   Modified: {stats['modified']}")
        print(f"   Skipped (already migrated): {stats['skipped']}")
        print(f"   Processed: {stats['processed']}")
