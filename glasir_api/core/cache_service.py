import databases
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

# Import the class, not the non-existent table variable
from glasir_api.models.db_models import TeacherCache

CACHE_DURATION_HOURS = 24  # Cache teacher map for 24 hours
log = logging.getLogger(__name__)

async def get_teacher_map_from_db(db: databases.Database) -> Optional[Dict[str, str]]:
    """
    Retrieves the teacher map from the cache by querying all non-expired entries.

    Args:
        db: The database connection instance.

    Returns:
        The cached teacher map as a dictionary {'initials': 'full_name'},
        or None if no valid cache entries are found.
    """
    teacher_map = {}
    now = datetime.now(timezone.utc)
    # Select all columns from non-expired entries
    query = TeacherCache.__table__.select().where(TeacherCache.__table__.c.expires_at > now)
    try:
        results = await db.fetch_all(query)
        if not results:
            log.info("No valid teacher cache entries found in DB.")
            return None

        for row in results:
            teacher_map[row["initials"]] = row["full_name"]

        log.info(f"Retrieved {len(teacher_map)} valid teacher entries from cache.")
        return teacher_map
    except Exception as e:
        log.error(f"Error fetching teacher map from cache: {e}", exc_info=True)
        return None


async def update_teacher_cache_in_db(db: databases.Database, teacher_map: Dict[str, str]) -> None:
    """
    Updates or inserts teacher cache entries in the database using an upsert strategy.

    Args:
        db: The database connection instance.
        teacher_map: The teacher map dictionary {'initials': 'full_name'} to cache.
    """
    if not teacher_map:
        log.warning("Attempted to update teacher cache with an empty map. Skipping.")
        return

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=CACHE_DURATION_HOURS)
    records_to_upsert = []
    for initials, full_name in teacher_map.items():
        records_to_upsert.append({
            "initials": initials,
            "full_name": full_name,
            "cached_at": now,
            "expires_at": expires_at
        })

    if not records_to_upsert:
        return # Should not happen if teacher_map was not empty, but safety check

    # Use transaction for atomicity
    async with db.transaction():
        try:
            # Database specific upsert logic might be needed here.
            # For SQLite, we can use INSERT OR REPLACE or ON CONFLICT UPDATE.
            # The 'databases' library doesn't directly support dialect-specific clauses easily.
            # A common pattern is to try insert and catch integrity error, then update,
            # or delete existing and insert new ones.
            # Simpler approach for now: Delete existing for these initials and insert new.

            # Get all initials from the input map
            initials_list = list(teacher_map.keys())

            # Delete existing entries for the initials we are about to insert/update
            delete_query = TeacherCache.__table__.delete().where(
                TeacherCache.__table__.c.initials.in_(initials_list)
            )
            await db.execute(delete_query)
            log.debug(f"Deleted existing cache entries for initials: {initials_list}")

            # Insert the new/updated records
            insert_query = TeacherCache.__table__.insert()
            await db.execute_many(query=insert_query, values=records_to_upsert)
            log.info(f"Upserted {len(records_to_upsert)} teacher cache entries.")

        except Exception as e:
            log.error(f"Error updating teacher cache in DB: {e}", exc_info=True)
            # Transaction will be rolled back automatically
            raise # Re-raise the exception after logging