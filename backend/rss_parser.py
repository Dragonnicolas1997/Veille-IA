import re
from urllib.parse import urlparse, urlunparse
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    """Normalize a URL to avoid near-duplicate entries (double slashes, trailing slash, etc.)."""
    parsed = urlparse(url)
    # Collapse multiple slashes in path
    path = re.sub(r'/+', '/', parsed.path)
    # Remove trailing slash (except root)
    if path != '/':
        path = path.rstrip('/')
    return urlunparse(parsed._replace(path=path, fragment=''))

# Common Atom namespace
ATOM_NS = "{http://www.w3.org/2005/Atom}"

# ── Pré-filtrage mots-clés IA ────────────────────────────────────
# Articles dont le titre OU la description contient au moins un de ces termes
AI_KEYWORDS = [
    # Termes généraux IA
    r"\bai\b", r"\ba\.i\.\b", r"artificial.intelligence",
    r"intelligence.artificielle", r"\bia\b",
    # Machine Learning / Deep Learning
    r"machine.learning", r"deep.learning", r"apprentissage.automatique",
    r"apprentissage.profond", r"neural.network", r"réseau.de.neurones",
    # LLMs et modèles
    r"\bllm\b", r"large.language.model", r"language.model",
    r"foundation.model", r"modèle.de.langage", r"grand.modèle",
    # Noms de modèles / acteurs clés
    r"\bgpt\b", r"gpt-[0-9]", r"\bchatgpt\b", r"\bopenai\b",
    r"\bclaude\b", r"\banthropic\b", r"\bgemini\b", r"\bgemma\b",
    r"\bmistral\b", r"\bllama\b", r"\bcopilot\b", r"\bmidjourney\b",
    r"\bstable.diffusion\b", r"\bdall-?e\b", r"\bsora\b",
    r"\bhugging.?face\b", r"\bdeepseek\b", r"\bperplexity\b",
    r"\bgrok\b", r"\bcohere\b",
    # IA générative
    r"generative.ai", r"gen.?ai\b", r"ia.générative", r"ia.generative",
    r"génération.de.texte", r"génération.d.?image",
    # Agents / automatisation IA
    r"\bagent.?ia\b", r"\bai.agent", r"agentic", r"agent.autonome",
    r"autonomous.agent",
    # NLP / Vision
    r"\bnlp\b", r"natural.language.processing",
    r"traitement.du.langage", r"computer.vision", r"vision.par.ordinateur",
    # Réglementation IA
    r"ai.act", r"loi.sur.l.?ia", r"régulation.*(ia|ai)",
    r"éthique.*(ia|ai)", r"(ia|ai).*éthique",
    r"biais.algorith", r"algorithmic.bias",
    # Transformation IA en entreprise
    r"(ia|ai).en.entreprise", r"transformation.*(ia|ai)",
    r"(ia|ai).*transformation", r"adoption.*(ia|ai)",
    r"déploiement.*(ia|ai)", r"stratégie.*(ia|ai)",
    # Termes techniques courants
    r"\btransformer\b", r"fine.?tuning", r"\brag\b",
    r"retrieval.augmented", r"prompt.engineering",
    r"reinforcement.learning", r"apprentissage.par.renforcement",
    r"\brobot", r"\bautomati",
]

_AI_PATTERN = re.compile("|".join(AI_KEYWORDS), re.IGNORECASE)


def is_ai_related_keyword(title: str, description: str) -> bool:
    """Pré-filtre rapide par mots-clés — True si l'article mentionne l'IA."""
    text = f"{title} {description}"
    return bool(_AI_PATTERN.search(text))


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    date_str = date_str.strip()
    # Try RFC 2822 (RSS 2.0)
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        pass
    # Try ISO 8601 (Atom)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).isoformat()
        except ValueError:
            continue
    return None


def _text(el, tag: str) -> str:
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _parse_rss(root, feed_id: int) -> list[dict]:
    articles = []
    for item in root.iter("item"):
        url = _text(item, "link")
        if not url:
            continue
        articles.append({
            "feed_id": feed_id,
            "title": _text(item, "title"),
            "url": _normalize_url(url),
            "description": _text(item, "description")[:2000],
            "published_at": _parse_date(_text(item, "pubDate")),
        })
    return articles


def _parse_atom(root, feed_id: int) -> list[dict]:
    articles = []
    for entry in root.iter(f"{ATOM_NS}entry"):
        # Atom links are in <link> element with href attribute
        link_el = entry.find(f"{ATOM_NS}link[@rel='alternate']")
        if link_el is None:
            link_el = entry.find(f"{ATOM_NS}link")
        url = link_el.get("href", "") if link_el is not None else ""
        if not url:
            continue

        summary = _text(entry, f"{ATOM_NS}summary") or _text(entry, f"{ATOM_NS}content")
        articles.append({
            "feed_id": feed_id,
            "title": _text(entry, f"{ATOM_NS}title"),
            "url": _normalize_url(url),
            "description": summary[:2000],
            "published_at": _parse_date(
                _text(entry, f"{ATOM_NS}published") or _text(entry, f"{ATOM_NS}updated")
            ),
        })
    return articles


async def fetch_url_metadata(url: str) -> dict:
    """Fetch a web page and extract its title and meta description."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "VeilleIA/1.0"
            })
            resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch URL {url}: {e}")
        return {"title": url, "description": ""}

    html = resp.text
    # Extract <title>
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = m.group(1).strip() if m else url
    # Extract <meta name="description">
    m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
            html, re.IGNORECASE | re.DOTALL,
        )
    description = m.group(1).strip() if m else ""

    # Clean HTML entities
    import html as html_mod
    title = html_mod.unescape(title)
    description = html_mod.unescape(description)

    return {"title": title[:500], "description": description[:2000]}


async def fetch_feed(feed_id: int, feed_url: str) -> list[dict]:
    """Fetch and parse a single RSS/Atom feed. Returns list of article dicts."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(feed_url, headers={
                "User-Agent": "VeilleIA/1.0 RSS Reader"
            })
            resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch {feed_url}: {e}")
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        logger.error(f"XML parse error for {feed_url}: {e}")
        return []

    # Detect format
    if root.tag == "rss" or root.find("channel") is not None:
        return _parse_rss(root, feed_id)
    elif root.tag == f"{ATOM_NS}feed" or root.tag == "feed":
        return _parse_atom(root, feed_id)
    else:
        logger.warning(f"Unknown feed format for {feed_url}: root tag = {root.tag}")
        return []


async def fetch_and_store(db) -> list[dict]:
    """Fetch all active feeds, deduplicate, insert new articles. Returns new articles."""
    cursor = await db.execute("SELECT id, url FROM feeds WHERE active = 1")
    feeds = await cursor.fetchall()

    all_new = []
    total_raw = 0
    total_filtered = 0
    for feed in feeds:
        articles = await fetch_feed(feed["id"], feed["url"])
        total_raw += len(articles)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        for article in articles:
            # Ignorer les articles sans date ou trop vieux
            if not article["published_at"] or article["published_at"] < cutoff:
                continue
            # Pré-filtrage par mots-clés : on ne garde que les articles liés à l'IA
            if not is_ai_related_keyword(article["title"], article["description"]):
                continue
            total_filtered += 1
            try:
                await db.execute(
                    """INSERT OR IGNORE INTO articles
                       (feed_id, url, title, description, published_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        article["feed_id"],
                        article["url"],
                        article["title"],
                        article["description"],
                        article["published_at"],
                    ),
                )
                # Check if it was actually inserted (not a duplicate)
                if db.total_changes:
                    all_new.append(article)
            except Exception as e:
                logger.error(f"DB insert error for {article['url']}: {e}")

        # Update last_fetched
        await db.execute(
            "UPDATE feeds SET last_fetched = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), feed["id"]),
        )

    logger.info(
        f"Pré-filtrage : {total_filtered}/{total_raw} articles passent le filtre mots-clés IA"
    )

    await db.commit()
    return all_new
