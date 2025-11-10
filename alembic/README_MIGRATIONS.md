# MVidarr Database Migrations

MVidarr uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations.

## Quick Start

### Check Current Migration Status
```bash
python3 scripts/manage_migrations.py current
```

### Upgrade to Latest Version
```bash
python3 scripts/manage_migrations.py upgrade
```

### View Migration History
```bash
python3 scripts/manage_migrations.py history
```

## Common Operations

### Upgrade Database
```bash
# Upgrade to latest version
python3 scripts/manage_migrations.py upgrade

# Upgrade one version forward
python3 scripts/manage_migrations.py upgrade +1

# Upgrade to specific revision
python3 scripts/manage_migrations.py upgrade <revision_id>
```

### Downgrade Database
```bash
# Downgrade one version back
python3 scripts/manage_migrations.py downgrade -1

# Downgrade to specific revision
python3 scripts/manage_migrations.py downgrade <revision_id>

# Downgrade to base (empty database)
python3 scripts/manage_migrations.py downgrade base
```

### Create New Migration

**Manual Migration:**
```bash
python3 scripts/manage_migrations.py create "add user preferences table"
```

**Auto-generated Migration (from model changes):**
```bash
python3 scripts/manage_migrations.py autogenerate "add email field to users"
```

**⚠️ IMPORTANT:** Always review auto-generated migrations before applying!

## Migration Files

Migrations are stored in `alembic/versions/` as Python files.

Each migration has:
- **Revision ID**: Unique identifier for the migration
- **upgrade()**: Function to apply the migration
- **downgrade()**: Function to revert the migration

## Configuration

### Database Connection
Database connection is configured automatically from MVidarr's `Config` class.
It reads from environment variables or `.env` file:
- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`

### Alembic Configuration
- `alembic.ini`: Main configuration file
- `alembic/env.py`: Environment setup (imports models, configures connection)

## Development Workflow

### Adding a New Model/Field

1. **Update SQLAlchemy models** in `src/database/models.py`
2. **Create migration**:
   ```bash
   python3 scripts/manage_migrations.py autogenerate "add new_field to table_name"
   ```
3. **Review the generated migration** in `alembic/versions/`
4. **Test migration**:
   ```bash
   # Apply migration
   python3 scripts/manage_migrations.py upgrade

   # Test rollback
   python3 scripts/manage_migrations.py downgrade -1

   # Re-apply
   python3 scripts/manage_migrations.py upgrade
   ```
5. **Commit migration file** to git

### Migration Best Practices

✅ **DO:**
- Always review auto-generated migrations
- Test both upgrade AND downgrade
- Keep migrations small and focused
- Add descriptive commit messages
- Include data migrations when schema changes affect existing data
- Test migrations on development database first

❌ **DON'T:**
- Modify existing migration files after they're committed
- Skip testing downgrades
- Mix schema changes with data changes
- Delete migration files
- Change revision IDs

## Troubleshooting

### "Can't locate revision identified by 'xyz'"
Your database stamp doesn't match any migration file. Use:
```bash
python3 scripts/manage_migrations.py stamp head
```

### "Target database is not up to date"
Run upgrade before creating new migrations:
```bash
python3 scripts/manage_migrations.py upgrade
```

### Migration Conflicts
If you have multiple branches with migrations:
1. Resolve revision order
2. Use `alembic merge` if needed
3. Contact team lead

### Reset Database (Development Only!)
```bash
# Drop all tables
python3 scripts/manage_migrations.py downgrade base

# Re-apply all migrations
python3 scripts/manage_migrations.py upgrade head
```

## Advanced Usage

### Direct Alembic Commands
```bash
# From project root
python3 -m alembic <command>
```

### Stamping Database
Mark database as being at a specific revision without running migrations:
```bash
python3 scripts/manage_migrations.py stamp head
```

**⚠️ WARNING:** Only use stamp if you know the database schema matches the revision!

## CI/CD Integration

Migrations should be run automatically during deployment:

```bash
# In deployment script
python3 scripts/manage_migrations.py upgrade
```

## Additional Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://www.sqlalchemy.org/)
- MVidarr model definitions: `src/database/models.py`
- Migration management script: `scripts/manage_migrations.py`
