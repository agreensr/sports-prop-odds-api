"""
Base repository class for data access layer.

The repository pattern provides:
1. Separation of data access logic from business logic
2. Single place for query logic (easier to maintain)
3. Easier testing (can mock repositories)
4. Consistent interface for data operations

Example:
    class PlayerRepository(BaseRepository[Player]):
        def find_by_external_id(self, external_id: str) -> Optional[Player]:
            return self.db.query(Player).filter(
                Player.external_id == external_id
            ).first()
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Type, Optional, List, Any, Dict
from datetime import datetime
from sqlalchemy import desc, func, or_, and_
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql.selectable import Select

T = TypeVar("T")


class BaseRepository(Generic[T], ABC):
    """
    Base repository class providing common data access methods.

    All repositories should extend this class and specify their model type.

    Attributes:
        model_type: The SQLAlchemy model class this repository manages
        db: The database session
    """

    def __init__(self, model_type: Type[T], db: Session):
        """
        Initialize the repository.

        Args:
            model_type: The SQLAlchemy model class
            db: The database session
        """
        self.model_type = model_type
        self.db = db

    # ========================================================================
    # CRUD Operations - Basic Create, Read, Update, Delete
    # ========================================================================

    def find_by_id(self, id: str) -> Optional[T]:
        """Find a single record by ID."""
        return self.db.query(self.model_type).filter(self.model_type.id == id).first()

    def find_all(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[str] = None
    ) -> List[T]:
        """
        Find all records with optional pagination.

        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            order_by: Column name to order by (prefix with '-' for descending)

        Returns:
            List of records
        """
        query = self.db.query(self.model_type)

        if order_by:
            if order_by.startswith('-'):
                column = getattr(self.model_type, order_by[1:])
                query = query.order_by(desc(column))
            else:
                column = getattr(self.model_type, order_by)
                query = query.order_by(column)

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        return query.all()

    def create(self, **kwargs) -> T:
        """
        Create a new record.

        Returns:
            The created record (not yet committed to database)
        """
        instance = self.model_type(**kwargs)
        self.db.add(instance)
        return instance

    def create_many(self, items: List[Dict[str, Any]]) -> List[T]:
        """
        Create multiple records in bulk.

        Args:
            items: List of dictionaries with record data

        Returns:
            List of created records (not yet committed)
        """
        instances = [self.model_type(**item) for item in items]
        self.db.add_all(instances)
        return instances

    def update(self, id: str, **kwargs) -> Optional[T]:
        """
        Update a record by ID.

        Returns:
            The updated record, or None if not found
        """
        instance = self.find_by_id(id)
        if instance:
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            instance.updated_at = datetime.utcnow()
        return instance

    def delete(self, id: str) -> bool:
        """
        Delete a record by ID.

        Returns:
            True if deleted, False if not found
        """
        instance = self.find_by_id(id)
        if instance:
            self.db.delete(instance)
            return True
        return False

    # ========================================================================
    # Query Builders - Flexible query construction
    # ========================================================================

    def query(self) -> Query:
        """Get a new query object for this model."""
        return self.db.query(self.model_type)

    def filter_by(self, **kwargs) -> List[T]:
        """Filter records by keyword arguments."""
        return self.db.query(self.model_type).filter_by(**kwargs).all()

    def filter_by_first(self, **kwargs) -> Optional[T]:
        """Filter records by keyword arguments and return first match."""
        return self.db.query(self.model_type).filter_by(**kwargs).first()

    def where(self, *criterion) -> List[T]:
        """Filter records using SQLAlchemy expressions."""
        return self.db.query(self.model_type).filter(*criterion).all()

    def where_first(self, *criterion) -> Optional[T]:
        """Filter records using SQLAlchemy expressions and return first match."""
        return self.db.query(self.model_type).filter(*criterion).first()

    # ========================================================================
    # Existence Checks
    # ========================================================================

    def exists(self, id: str) -> bool:
        """Check if a record with given ID exists."""
        return self.db.query(
            self.db.query(self.model_type).filter(self.model_type.id == id).exists()
        ).scalar()

    def exists_where(self, *criterion) -> bool:
        """Check if any record matching the criterion exists."""
        return self.db.query(
            self.db.query(self.model_type).filter(*criterion).exists()
        ).scalar()

    def count(self, *criterion) -> int:
        """Count records matching optional criterion."""
        query = self.db.query(func.count(self.model_type.id))
        if criterion:
            query = query.filter(*criterion)
        return query.scalar() or 0

    # ========================================================================
    # Date Range Queries
    # ========================================================================

    def in_date_range(
        self,
        date_field: str,
        start: datetime,
        end: datetime,
        *additional_criterion
    ) -> List[T]:
        """
        Find records within a date range.

        Args:
            date_field: Name of the datetime field to filter on
            start: Start date (inclusive)
            end: End date (inclusive)
            additional_criterion: Additional filter criteria

        Returns:
            List of records within the date range
        """
        column = getattr(self.model_type, date_field)
        query = self.db.query(self.model_type).filter(
            column >= start,
            column <= end
        )
        if additional_criterion:
            query = query.filter(*additional_criterion)
        return query.all()

    def recent(
        self,
        date_field: str,
        days: int = 7,
        *additional_criterion
    ) -> List[T]:
        """
        Find records from the last N days.

        Args:
            date_field: Name of the datetime field to filter on
            days: Number of days to look back
            additional_criterion: Additional filter criteria

        Returns:
            List of recent records
        """
        from datetime import timedelta, timezone

        try:
            utc = timezone.utc
        except AttributeError:
            from datetime import timezone as tz
            utc = tz.utc

        cutoff = datetime.now(utc).replace(tzinfo=None) - timedelta(days=days)
        column = getattr(self.model_type, date_field)
        query = self.db.query(self.model_type).filter(column >= cutoff)
        if additional_criterion:
            query = query.filter(*additional_criterion)
        return query.all()

    # ========================================================================
    # Aggregation Methods
    # ========================================================================

    def group_by_and_count(
        self,
        group_field: str,
        *additional_criterion,
        order_by_count: bool = True,
        descending: bool = True
    ) -> List[tuple]:
        """
        Group by a field and count records in each group.

        Args:
            group_field: Name of the field to group by
            additional_criterion: Additional filter criteria
            order_by_count: Whether to order by count (default True)
            descending: Order direction (default True for descending)

        Returns:
            List of tuples: [(group_value, count), ...]
        """
        column = getattr(self.model_type, group_field)
        query = self.db.query(column, func.count(self.model_type.id))

        if additional_criterion:
            query = query.filter(*additional_criterion)

        query = query.group_by(column)

        if order_by_count:
            if descending:
                query = query.order_by(desc(func.count(self.model_type.id)))
            else:
                query = query.order_by(func.count(self.model_type.id))

        return query.all()

    # ========================================================================
    # Batch Operations
    # ========================================================================

    def bulk_create(
        self,
        items: List[Dict[str, Any]],
        return_defaults: bool = True
    ) -> List[T]:
        """
        Bulk insert records for better performance.

        Args:
            items: List of dictionaries with record data
            return_defaults: Whether to return generated IDs

        Returns:
            List of created records
        """
        if not items:
            return []

        instances = [self.model_type(**item) for item in items]
        self.db.bulk_save_objects(instances, return_defaults=return_defaults)
        return instances

    def bulk_update(self, items: List[Dict[str, Any]]) -> None:
        """
        Bulk update records.

        Args:
            items: List of dictionaries with record data (must include 'id')
        """
        for item in items:
            if 'id' in item:
                id_value = item.pop('id')
                self.db.query(self.model_type).filter(
                    self.model_type.id == id_value
                ).update(item)

    # ========================================================================
    # Save Operations
    # ========================================================================

    def save(self) -> None:
        """Commit pending changes to the database."""
        self.db.commit()

    def flush(self) -> None:
        """Flush pending changes without committing."""
        self.db.flush()

    def refresh(self, instance: T) -> T:
        """Refresh an instance from the database."""
        self.db.refresh(instance)
        return instance

    def rollback(self) -> None:
        """Rollback pending changes."""
        self.db.rollback()
