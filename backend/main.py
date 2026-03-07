from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path

import anthropic

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import get_db, init_db
from rss_parser import fetch_and_store, is_ai_related_keyword
from claude_service import (
    get_api_key,
    filter_and_classify,
    apply_classifications,
    generate_briefing,
    generate_briefing_with_prompt,
)
from scheduler import start_scheduler, reschedule
from dedup import deduplicate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await start_scheduler()
    yield


app = FastAPI(title="Veille IA", lifespan=lifespan)

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ──────────────────────────────────────────────

class FeedIn(BaseModel):
    url: str
    name: str

class CategoryIn(BaseModel):
    name: str
    color: str = "#6b7280"
    description: str = ""
    position: int = 0

class ArticlePatch(BaseModel):
    category_id: int | None = None
    manually_removed: bool | None = None

class SettingsIn(BaseModel):
    anthropic_api_key: str | None = None
    refresh_interval_hours: int | None = None

class BriefingIn(BaseModel):
    article_ids: list[int] = []
    auto: bool = False
    prompt: str | None = None


# ── Feeds ─────────────────────────────────────────────────────────

@app.get("/api/feeds")
async def list_feeds():
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM feeds ORDER BY created_at DESC")
        return [dict(row) for row in await cursor.fetchall()]
    finally:
        await db.close()


@app.post("/api/feeds", status_code=201)
async def add_feed(feed: FeedIn):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO feeds (url, name) VALUES (?, ?)", (feed.url, feed.name)
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM feeds WHERE url = ?", (feed.url,))
        return dict(await cursor.fetchone())
    except Exception:
        raise HTTPException(400, "Feed URL already exists")
    finally:
        await db.close()


@app.delete("/api/feeds/{feed_id}")
async def delete_feed(feed_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# ── Refresh ───────────────────────────────────────────────────────

async def _categories_hash(db) -> str:
    """Compute a hash of all category descriptions to detect changes."""
    cursor = await db.execute("SELECT name, description FROM categories ORDER BY id")
    rows = await cursor.fetchall()
    content = "|".join(f"{r['name']}:{r['description'] or ''}" for r in rows)
    return hashlib.sha256(content.encode()).hexdigest()


async def _check_and_reclassify(db, api_key) -> int:
    """If category descriptions changed since last classification, reclassify all articles."""
    current_hash = await _categories_hash(db)

    cursor = await db.execute("SELECT value FROM settings WHERE key = 'categories_hash'")
    row = await cursor.fetchone()
    stored_hash = row["value"] if row else None

    if stored_hash == current_hash:
        return 0

    logger.info("Category descriptions changed — reclassifying articles")

    cursor = await db.execute("SELECT id, name, description FROM categories ORDER BY position")
    categories = [dict(row) for row in await cursor.fetchall()]

    # Reclassify: visible articles + recent unclassified (last 7 days)
    cursor = await db.execute(
        """SELECT id, url, title, description, published_at FROM articles
           WHERE manually_removed = 0 AND relevance_score <> -1
           AND (is_ai_related = 1 OR published_at >= datetime('now', '-7 days'))
           ORDER BY published_at DESC"""
    )
    pool = [dict(row) for row in await cursor.fetchall()]
    pool = deduplicate(pool, title_key="title", date_key="published_at")
    logger.info(f"Reclassify: {len(pool)} articles to process")

    classified = 0
    if pool:
        results = await filter_and_classify(pool, categories, api_key)
        await apply_classifications(db, results)
        classified = len(results)

    # Store new hash
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ("categories_hash", current_hash),
    )
    await db.commit()
    return classified


@app.post("/api/feeds/refresh")
async def refresh_feeds():
    db = await get_db()
    try:
        new_articles = await fetch_and_store(db)
        count_new = len(new_articles)

        api_key = await get_api_key(db)
        classified = 0
        reclassified = 0
        keyword_rejected = 0

        if api_key:
            # 0. Check if categories changed → reclassify everything
            reclassified = await _check_and_reclassify(db, api_key)

        # 1. Pré-filtre mots-clés sur les articles non traités (derniers 14 jours)
        cursor = await db.execute(
            """SELECT id, title, description FROM articles
               WHERE is_ai_related = 0 AND relevance_score = 0 AND manually_removed = 0
               AND fetched_at >= datetime('now', '-7 days')"""
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
                keyword_rejected += 1

        if keyword_rejected:
            await db.commit()
            logger.info(f"Pré-filtre mots-clés : {keyword_rejected} articles écartés, {len(candidates)} candidats")

        # 2. Envoyer les candidats à Claude pour classification fine
        if api_key and candidates:
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
            # Limiter pour garder un refresh rapide (~30s max)
            pool = pool[:200]
            logger.info(f"Après dédup : {len(pool)} articles à classifier")

            if pool:
                results = await filter_and_classify(pool, categories, api_key)
                await apply_classifications(db, results)
                classified = len(results)

        return {
            "new_articles": count_new,
            "reclassified": reclassified,
            "keyword_rejected": keyword_rejected,
            "sent_to_claude": len(candidates) if api_key else 0,
            "classified": classified,
        }
    finally:
        await db.close()


@app.post("/api/reclassify")
async def reclassify_articles():
    """Re-classify all keyword-passed articles with current category descriptions."""
    db = await get_db()
    try:
        api_key = await get_api_key(db)
        if not api_key:
            raise HTTPException(400, "Clé API Anthropic non configurée")

        cursor = await db.execute(
            "SELECT id, name, description FROM categories ORDER BY position"
        )
        categories = [dict(row) for row in await cursor.fetchall()]

        # Reclassify: visible articles + recent unclassified (last 7 days)
        cursor = await db.execute(
            """SELECT id, url, title, description, published_at FROM articles
               WHERE manually_removed = 0 AND relevance_score <> -1
               AND (is_ai_related = 1 OR published_at >= datetime('now', '-7 days'))
               ORDER BY published_at DESC"""
        )
        pool = [dict(row) for row in await cursor.fetchall()]
        pool = deduplicate(pool, title_key="title", date_key="published_at")
        logger.info(f"Reclassify: {len(pool)} articles to process")

        classified = 0
        if pool:
            results = await filter_and_classify(pool, categories, api_key)
            await apply_classifications(db, results)
            classified = len(results)

        # Update hash so refresh won't reclassify again
        new_hash = await _categories_hash(db)
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("categories_hash", new_hash),
        )
        await db.commit()

        return {"reclassified": classified}
    finally:
        await db.close()


@app.post("/api/reclassify-rejected")
async def reclassify_rejected():
    """Re-classify previously rejected articles (score 0-6) with updated criteria."""
    db = await get_db()
    try:
        api_key = await get_api_key(db)
        if not api_key:
            raise HTTPException(400, "Clé API Anthropic non configurée")

        cursor = await db.execute(
            "SELECT id, name, description FROM categories ORDER BY position"
        )
        categories = [dict(row) for row in await cursor.fetchall()]

        # Fetch articles that were classified but rejected (score 0-6, not keyword-rejected)
        # Also include keyword-rejected (-1) from the last 14 days for a fresh look
        cursor = await db.execute(
            """SELECT id, url, title, description, published_at FROM articles
               WHERE manually_removed = 0
               AND (
                   (relevance_score BETWEEN 1 AND 6)
                   OR (relevance_score = -1 AND fetched_at >= datetime('now', '-14 days'))
                   OR (is_ai_related = 0 AND relevance_score = 0 AND fetched_at >= datetime('now', '-14 days'))
               )
               ORDER BY published_at DESC"""
        )
        pool = [dict(row) for row in await cursor.fetchall()]
        pool = deduplicate(pool, title_key="title", date_key="published_at")
        pool = pool[:500]  # Limit to avoid excessive API calls
        logger.info(f"Reclassify-rejected: {len(pool)} articles to reprocess")

        classified = 0
        if pool:
            results = await filter_and_classify(pool, categories, api_key)
            await apply_classifications(db, results)
            classified = len(results)

        return {"reprocessed": len(pool), "classified": classified}
    finally:
        await db.close()


# ── Articles ──────────────────────────────────────────────────────

@app.get("/api/articles")
async def list_articles(
    category_id: int | None = Query(None),
    days: int | None = Query(None, ge=1, le=31),
    per_category: int = Query(100, ge=1, le=200),
):
    db = await get_db()
    try:
        # Filtre de base — exclure les articles sans date
        where = "a.is_ai_related = 1 AND a.manually_removed = 0 AND a.published_at IS NOT NULL"
        params: list = []

        if category_id is not None:
            where += " AND a.category_id = ?"
            params.append(category_id)

        if days is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            where += " AND a.published_at >= ?"
            params.append(cutoff)

        # Top N par catégorie via ROW_NUMBER()
        params.append(per_category)
        query = f"""
            SELECT * FROM (
                SELECT a.*, f.name as feed_name, c.name as category_name, c.color as category_color,
                       ROW_NUMBER() OVER (
                           PARTITION BY a.category_id
                           ORDER BY a.relevance_score DESC, a.published_at DESC
                       ) as rn
                FROM articles a
                LEFT JOIN feeds f ON a.feed_id = f.id
                LEFT JOIN categories c ON a.category_id = c.id
                WHERE {where}
            ) WHERE rn <= ?
            ORDER BY relevance_score DESC, published_at DESC
        """

        cursor = await db.execute(query, params)
        articles = [dict(row) for row in await cursor.fetchall()]

        # Dédupliquer les articles similaires (garder le meilleur score par sujet)
        articles = deduplicate(
            articles, title_key="title",
            score_key="relevance_score", date_key="published_at",
        )

        return articles
    finally:
        await db.close()


@app.patch("/api/articles/{article_id}")
async def update_article(article_id: int, patch: ArticlePatch):
    db = await get_db()
    try:
        updates, params = [], []
        if patch.category_id is not None:
            updates.append("category_id = ?")
            params.append(patch.category_id)
        if patch.manually_removed is not None:
            updates.append("manually_removed = ?")
            params.append(1 if patch.manually_removed else 0)
        if not updates:
            raise HTTPException(400, "No fields to update")

        params.append(article_id)
        await db.execute(
            f"UPDATE articles SET {', '.join(updates)} WHERE id = ?", params
        )
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# ── Categories ────────────────────────────────────────────────────

@app.get("/api/categories")
async def list_categories():
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM categories ORDER BY position")
        return [dict(row) for row in await cursor.fetchall()]
    finally:
        await db.close()


@app.post("/api/categories", status_code=201)
async def create_category(cat: CategoryIn):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO categories (name, color, description, position) VALUES (?, ?, ?, ?)",
            (cat.name, cat.color, cat.description, cat.position),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM categories WHERE name = ?", (cat.name,))
        return dict(await cursor.fetchone())
    finally:
        await db.close()


@app.put("/api/categories/{cat_id}")
async def update_category(cat_id: int, cat: CategoryIn):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE categories SET name=?, color=?, description=?, position=? WHERE id=?",
            (cat.name, cat.color, cat.description, cat.position, cat_id),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Category not found")
        return dict(row)
    finally:
        await db.close()


@app.delete("/api/categories/{cat_id}")
async def delete_category(cat_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# ── Settings ──────────────────────────────────────────────────────

def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@app.get("/api/settings")
async def get_settings():
    db = await get_db()
    try:
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        result = {}
        for row in rows:
            k, v = row["key"], row["value"]
            if k == "anthropic_api_key":
                # Return masked version
                result[k] = "sk-***" if v else ""
            else:
                result[k] = v
        return result
    finally:
        await db.close()


@app.put("/api/settings")
async def update_settings(s: SettingsIn):
    db = await get_db()
    try:
        if s.anthropic_api_key is not None:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("anthropic_api_key", s.anthropic_api_key),
            )
        if s.refresh_interval_hours is not None:
            hours = max(1, s.refresh_interval_hours)
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("refresh_interval_hours", str(hours)),
            )
            await reschedule(hours)
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# ── Briefing ──────────────────────────────────────────────────────

@app.post("/api/briefing")
async def create_briefing(body: BriefingIn):
    db = await get_db()
    try:
        api_key = await get_api_key(db)
        if not api_key:
            raise HTTPException(400, "Clé API Anthropic non configurée")

        if body.prompt:
            # Prompt mode: Claude selects articles based on user request
            cursor = await db.execute(
                """SELECT a.id, a.url, a.title, a.title_fr, a.summary_fr, a.relevance_score,
                          c.name as category_name
                   FROM articles a
                   LEFT JOIN categories c ON a.category_id = c.id
                   WHERE a.is_ai_related = 1 AND a.manually_removed = 0
                   ORDER BY a.relevance_score DESC"""
            )
            all_arts = [dict(r) for r in await cursor.fetchall()]
            if not all_arts:
                raise HTTPException(400, "Aucun article disponible")

            try:
                result = await generate_briefing_with_prompt(all_arts, body.prompt, api_key)
                return {"briefing": result["briefing"], "selected_ids": result["selected_ids"]}
            except Exception as e:
                logger.exception("Prompt briefing error")
                raise HTTPException(500, f"Erreur génération: {e}")

        elif body.auto:
            # Auto: top 2 articles per category
            cursor = await db.execute(
                """SELECT a.id, a.url, a.title, a.title_fr, a.summary_fr, c.name as category_name
                   FROM articles a
                   LEFT JOIN categories c ON a.category_id = c.id
                   WHERE a.is_ai_related = 1 AND a.manually_removed = 0
                   ORDER BY a.relevance_score DESC"""
            )
            all_arts = [dict(r) for r in await cursor.fetchall()]
            # Take top 2 per category
            per_cat = {}
            selected = []
            for a in all_arts:
                cat = a.get("category_name", "Autre")
                per_cat.setdefault(cat, 0)
                if per_cat[cat] < 2:
                    selected.append(a)
                    per_cat[cat] += 1
        else:
            if not body.article_ids:
                raise HTTPException(400, "Aucun article sélectionné")
            placeholders = ",".join("?" for _ in body.article_ids)
            cursor = await db.execute(
                f"""SELECT a.id, a.url, a.title, a.title_fr, a.summary_fr, c.name as category_name
                    FROM articles a
                    LEFT JOIN categories c ON a.category_id = c.id
                    WHERE a.id IN ({placeholders})""",
                body.article_ids,
            )
            selected = [dict(r) for r in await cursor.fetchall()]

        if not selected:
            raise HTTPException(400, "Aucun article trouvé")

        text = await generate_briefing(selected, api_key)
        return {"briefing": text}
    finally:
        await db.close()


# ── Translate missing titles ─────────────────────────────────────

@app.post("/api/translate-titles")
async def translate_titles():
    """Translate titles of already-classified articles that lack title_fr."""
    db = await get_db()
    try:
        api_key = await get_api_key(db)
        if not api_key:
            raise HTTPException(400, "Clé API Anthropic non configurée")

        cursor = await db.execute(
            """SELECT id, title FROM articles
               WHERE is_ai_related = 1 AND (title_fr IS NULL OR title_fr = '')
               ORDER BY relevance_score DESC LIMIT 500"""
        )
        rows = [dict(r) for r in await cursor.fetchall()]
        if not rows:
            return {"translated": 0}

        client = anthropic.AsyncAnthropic(api_key=api_key)
        translated = 0

        for i in range(0, len(rows), 20):
            batch = rows[i:i+20]
            titles_json = json.dumps(
                [{"id": r["id"], "title": r["title"]} for r in batch],
                ensure_ascii=False,
            )
            try:
                response = await client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=4096,
                    system="Tu traduis des titres d'articles en français. Si le titre est déjà en français, garde-le tel quel. Réponds UNIQUEMENT avec un tableau JSON : [{\"id\": ..., \"title_fr\": ...}]. Pas de markdown, pas de texte autour.",
                    messages=[{"role": "user", "content": f"Traduis ces titres :\n{titles_json}"}],
                )
                text = response.content[0].text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1]
                    if text.endswith("```"):
                        text = text[:text.rfind("```")]
                results = json.loads(text)
                for r in results:
                    if r.get("id") and r.get("title_fr"):
                        await db.execute(
                            "UPDATE articles SET title_fr = ? WHERE id = ?",
                            (r["title_fr"], r["id"]),
                        )
                        translated += 1
            except Exception as e:
                logger.error(f"Translation batch error: {e}")

        await db.commit()
        return {"translated": translated}
    finally:
        await db.close()


# ── Stats ─────────────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) as total FROM articles WHERE is_ai_related = 1 AND manually_removed = 0"
        )
        total = (await cursor.fetchone())["total"]

        cursor = await db.execute(
            """SELECT c.name, c.color, COUNT(a.id) as count
               FROM categories c
               LEFT JOIN articles a ON a.category_id = c.id AND a.is_ai_related = 1 AND a.manually_removed = 0
               GROUP BY c.id ORDER BY c.position"""
        )
        per_category = [dict(row) for row in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT MAX(last_fetched) as last_refresh FROM feeds"
        )
        last_refresh = (await cursor.fetchone())["last_refresh"]

        return {
            "total_articles": total,
            "per_category": per_category,
            "last_refresh": last_refresh,
        }
    finally:
        await db.close()


# ── SPA static serving (production) ──────────────────────────────

STATIC_DIR = Path(__file__).resolve().parent / "static"

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file = STATIC_DIR / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")
