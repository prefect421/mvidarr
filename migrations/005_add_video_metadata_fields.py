"""
Migration 005: Add enhanced video metadata fields
Adds album and last_enriched fields to support enhanced metadata collection
"""

from sqlalchemy import text

def upgrade(connection):
    """Add new video metadata fields"""
    
    # Add album field to videos table
    try:
        connection.execute(text("""
            ALTER TABLE videos 
            ADD COLUMN album VARCHAR(500) NULL
        """))
        print("✓ Added album field to videos table")
    except Exception as e:
        print(f"⚠ Album field may already exist: {e}")
    
    # Add last_enriched field to videos table
    try:
        connection.execute(text("""
            ALTER TABLE videos 
            ADD COLUMN last_enriched DATETIME NULL
        """))
        print("✓ Added last_enriched field to videos table")
    except Exception as e:
        print(f"⚠ last_enriched field may already exist: {e}")
    
    print("✓ Migration 005 completed: Enhanced video metadata fields added")

def downgrade(connection):
    """Remove video metadata fields"""
    
    # Remove album field
    try:
        connection.execute(text("""
            ALTER TABLE videos 
            DROP COLUMN album
        """))
        print("✓ Removed album field from videos table")
    except Exception as e:
        print(f"⚠ Could not remove album field: {e}")
    
    # Remove last_enriched field  
    try:
        connection.execute(text("""
            ALTER TABLE videos 
            DROP COLUMN last_enriched
        """))
        print("✓ Removed last_enriched field from videos table")
    except Exception as e:
        print(f"⚠ Could not remove last_enriched field: {e}")
    
    print("✓ Migration 005 rollback completed")