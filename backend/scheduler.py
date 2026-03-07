from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging

from database import get_db
from rss_parser import fetch_and_store, is_ai_related_keyword
from claude_service import get_api_key, filter_and_classify, apply_classifications
from dedup import deduplicate

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
JOB_ID = "rss_refresh"


async def refresh_job():
    """Fetch feeds, pre-filter by keywords, run Claude analysis, update DB."""
    logger.info("Scheduled refresh starting...")
    db = await get_db()
    try:
        new_articles = await fetch_and_store(db)
        logger.info(f"Fetched {len(new_articles)} new articles")

        api_key = await get_api_key(db)
        if not api_key:
            logger.warning("No Anthropic API key configured — skipping classification")
            return

        # Pre-filter: keyword check on all unprocessed articles
        cursor = await db.execute(
            """SELECT id, title, description FROM articles
               WHERE is_ai_related = 0 AND relevance_score = 0 AND manually_removed = 0"""
        )
        unprocessed = [dict(row) for row in await cursor.fetchall()]

        candidates = []
        for art in unprocessed:
            if is_ai_related_keyword(art["title"], art["description"]):
                candidates.append(art["id"])
            else:
                await db.execute(
                    "UPDATE articles SET relevance_score = -1 WHERE id = ?",
                    (art["id"],),
                )
        await db.commit()

        if not candidates:
            logger.info("No candidates after keyword filter")
            return

        cursor = await db.execute(
            "SELECT id, name, description FROM categories ORDER BY position"
        )
        categories = [dict(row) for row in await cursor.fetchall()]

        placeholders = ",".join("?" for _ in candidates)
        cursor = await db.execute(
            f"""SELECT id, url, title, description, published_at FROM articles
                WHERE id IN ({placeholders})
                ORDER BY published_at DESC""",
            candidates,
        )
        pool = [dict(row) for row in await cursor.fetchall()]
        pool = deduplicate(pool, title_key="title", date_key="published_at")

        if pool:
            classifications = await filter_and_classify(pool, categories, api_key)
            await apply_classifications(db, classifications)
            logger.info(f"Classified {len(classifications)} articles")
    except Exception as e:
        logger.exception(f"Refresh job error: {e}")
    finally:
        await db.close()


async def cleanup_old_articles():
    """Delete articles older than 60 days."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM articles WHERE published_at < datetime('now', '-60 days')"
        )
        deleted = cursor.rowcount
        await db.commit()
        if deleted:
            logger.info(f"Cleanup: deleted {deleted} articles older than 60 days")
    except Exception as e:
        logger.exception(f"Cleanup job error: {e}")
    finally:
        await db.close()


async def start_scheduler():
    """Start the scheduler with the interval from settings."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = 'refresh_interval_hours'"
        )
        row = await cursor.fetchone()
        hours = int(row["value"]) if row else 4
    finally:
        await db.close()

    scheduler.add_job(
        refresh_job,
        trigger=IntervalTrigger(hours=hours),
        id=JOB_ID,
        replace_existing=True,
    )
    scheduler.add_job(
        cleanup_old_articles,
        trigger=IntervalTrigger(days=1),
        id="cleanup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started with {hours}h interval + daily cleanup")


async def reschedule(hours: int):
    """Update the scheduler interval dynamically."""
    if scheduler.get_job(JOB_ID):
        scheduler.reschedule_job(JOB_ID, trigger=IntervalTrigger(hours=hours))
        logger.info(f"Scheduler rescheduled to {hours}h interval")
