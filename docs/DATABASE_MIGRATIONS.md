# Database Migration System

MVidarr uses a custom database migration system to handle schema changes safely across different deployments and upgrades.

## Overview

The migration system ensures that database schema changes are applied consistently across all installations, preventing issues like the missing `thumbnail_url` column in the playlists table.

## Migration Components

### 1. Migration Framework (`src/database/migrations.py`)

- **Migration Class**: Base class for all database migrations
- **MigrationManager**: Handles migration execution and tracking
- **Migration Tracking**: Uses `database_migrations` table to track applied migrations

### 2. Automatic Migration Execution

Migrations are automatically executed during database initialization in `src/database/init_db.py`, on every application startup — there is currently no REST API for checking status or triggering migrations manually (an earlier Flask-era API at these paths was never carried over in the FastAPI migration). To check what's applied, query the `database_migrations` tracking table directly or read the startup log output.

## Creating New Migrations

### Step 1: Create Migration Class

Add new migration classes to `src/database/migrations.py`:

```python
class Migration_002_YourMigrationName(Migration):
    """Description of what this migration does"""

    def __init__(self):
        super().__init__("002", "Description of migration")

    def up(self, connection):
        """Apply the migration"""
        try:
            # Your migration SQL here
            connection.execute(text("ALTER TABLE example ADD COLUMN new_field VARCHAR(255) NULL"))
            logger.info("Added new_field column to example table")
        except Exception as e:
            logger.error(f"Failed to apply migration: {e}")
            raise

    def down(self, connection):
        """Rollback the migration (optional)"""
        try:
            connection.execute(text("ALTER TABLE example DROP COLUMN new_field"))
            logger.info("Removed new_field column from example table")
        except Exception as e:
            logger.error(f"Failed to rollback migration: {e}")
            raise
```

### Step 2: Register Migration

Add your migration to the migrations list in `MigrationManager.__init__()`:

```python
def __init__(self):
    self.migrations: List[Migration] = [
        Migration_001_AddPlaylistThumbnailUrl(),
        Migration_002_YourMigrationName(),  # Add here
        # Add new migrations here
    ]
```

### Step 3: Version Numbering

- Use sequential numbering: 001, 002, 003, etc.
- Use descriptive names: `Migration_001_AddPlaylistThumbnailUrl`
- Include purpose in description

## Migration Best Practices

### 1. Safety First

- Always check if changes already exist before applying
- Use `IF NOT EXISTS` or `SHOW COLUMNS` checks
- Handle errors gracefully with try/catch blocks

### 2. Backwards Compatibility

- Avoid breaking changes when possible
- Use NULL-able columns for new fields
- Provide default values for non-nullable columns

### 3. Testing

```python
def up(self, connection):
    # Check if column already exists
    result = connection.execute(text("SHOW COLUMNS FROM table_name LIKE 'column_name'"))
    if result.fetchone():
        logger.info("Column already exists, skipping")
        return
    
    # Apply migration
    connection.execute(text("ALTER TABLE table_name ADD COLUMN column_name VARCHAR(255) NULL"))
```

### 4. Rollback Support

Always implement the `down()` method when possible:

```python
def down(self, connection):
    """Rollback the migration"""
    connection.execute(text("ALTER TABLE table_name DROP COLUMN column_name"))
```

## Migration Execution

### Automatic Execution

Migrations run automatically when the application starts:

1. Database initialization calls `run_migrations()`
2. Migration manager checks for pending migrations
3. Applies migrations in version order
4. Records successful migrations in `database_migrations` table

### Manual/Rollback Execution

There is currently no REST API or CLI entry point for manually re-running or rolling back a specific migration outside of application startup. To roll back, either restore from a database backup taken before the migration, or connect directly and run the migration's `down()` SQL and delete its row from `database_migrations`.

## Migration Tracking

The system uses a `database_migrations` table:

```sql
CREATE TABLE database_migrations (
    version VARCHAR(10) PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    applied_at DATETIME NOT NULL,
    applied_by VARCHAR(100) DEFAULT 'system'
)
```

## Current Migrations

### Migration_001_AddPlaylistThumbnailUrl

**Version**: 001  
**Description**: Add thumbnail_url column to playlists table  
**Purpose**: Fixes missing column that caused 500 errors in playlist loading

**Changes**:
- Adds `thumbnail_url VARCHAR(500) NULL` to `playlists` table
- Positioned after `playlist_metadata` column

## Troubleshooting

### Migration Failures

1. **Check logs**: Migration errors are logged with details
2. **Database state**: Verify current schema matches expectations
3. **Partial failures**: Some migrations may need manual cleanup
4. **Rollback**: Use rollback functionality for failed migrations

### Common Issues

1. **Column already exists**: Migrations should check before applying
2. **Permission errors**: Ensure database user has ALTER privileges
3. **Constraint violations**: Handle foreign key and unique constraints
4. **Data migration**: Large data changes should be batched

### Recovery

If migrations fail:

1. Check application logs for specific error
2. Verify database connectivity and permissions
3. Manually inspect database schema
4. Use rollback if needed
5. Fix migration code and retry

## Docker Deployments

For Docker containers:

1. Migrations run automatically on container startup
2. Use persistent database volumes to maintain migration state
3. Health checks should verify migration completion
4. Rolling updates should handle schema changes gracefully

## Production Considerations

### Pre-deployment Testing

1. Test migrations on copy of production data
2. Verify rollback procedures work
3. Estimate migration execution time
4. Plan for downtime if needed

### Deployment Strategy

1. **Blue/Green**: Run migrations before switching traffic
2. **Rolling**: Ensure backward compatibility during transition
3. **Maintenance Window**: Schedule for large schema changes

### Monitoring

1. Monitor migration execution logs
2. Verify application functionality after migrations
3. Check database performance impact
4. Monitor for migration-related errors

## Future Enhancements

Planned improvements to the migration system:

1. **Schema Validation**: Verify expected schema state after migrations
2. **Data Migration Support**: Framework for data transformation migrations
3. **Dependency Management**: Handle migration dependencies and prerequisites
4. **Performance Optimization**: Batch operations for large data changes
5. **Backup Integration**: Automatic backups before major migrations