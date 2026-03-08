import aiosqlite
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "veille.db"))

SEED_FEEDS = [
    # Tech & Recherche
    ("https://huggingface.co/blog/feed.xml", "Hugging Face Blog"),
    ("https://www.technologyreview.com/feed/", "MIT Technology Review"),
    ("https://aws.amazon.com/blogs/machine-learning/feed/", "AWS Machine Learning Blog"),
    ("https://blogs.microsoft.com/ai/feed/", "Microsoft AI Blog"),
    # Innovation & Actualités
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch - AI"),
    ("https://venturebeat.com/category/ai/feed/", "VentureBeat - AI"),
    ("https://rss.app/feeds/MfzXXWYYW25v1YMe.xml", "L'Usine Digitale"),
    # Réglementaire & Éthique
    ("https://www.cnil.fr/fr/rss.xml", "CNIL - Actualités"),
    ("https://linc.cnil.fr/rss.xml", "LINC (CNIL)"),
    ("https://rss.app/feeds/Uq5zsW6lZLtmzBAs.xml", "Stanford HAI"),
    ("https://rss.app/feeds/w96fbMAi1jrm945u.xml", "OECD AI Policy Observatory"),
    ("https://rss.app/feeds/Si39ht64GROA17C7.xml", "World Economic Forum"),
    # Impacts Sociaux & RH
    ("https://www.strategie.gouv.fr/rss.xml", "France Stratégie"),
    ("https://rss.app/feeds/5keS8T8iWcv7B0qz.xml", "Harvard Business Review"),
    # Cas d'Usage & Marché
    ("https://www.journaldunet.com/rss/", "Journal du Net - IA"),
    ("https://www.mckinsey.com/insights/rss", "McKinsey Insights"),
    ("https://www.hub-franceia.fr/feed/", "Hub France IA"),
    ("https://www.cbinsights.com/research/feed/", "CB Insights"),
    ("https://rss.app/feeds/DTBeUkhTnXS7TtQH.xml", "Capgemini Research Institute"),
    ("https://news.microsoft.com/fr-fr/feed/", "Microsoft France"),
    ("https://www.maddyness.com/feed/", "Maddyness"),
    ("https://numeum.fr/feed/", "Numeum"),
    # Cabinets de conseil
    ("https://rss.app/feeds/OC8z0lI9kzPOGCY0.xml", "BCG Publications"),
    ("https://rss.app/feeds/Ry8cPt05z0pGDcz5.xml", "Deloitte Insights"),
    ("https://rss.app/feeds/C5JTkle1OFVzki8C.xml", "EY Newsroom"),
    ("https://rss.app/feeds/Hdh9fkcidmuErDsy.xml", "KPMG Insights"),
    ("https://rss.app/feeds/aNsUrJodDVyXogQC.xml", "Accenture Newsroom"),
    ("https://rss.app/feeds/eVy2BnY5GsfOGVoC.xml", "Bain Insights"),
    ("https://rss.app/feeds/Q1jvNVWtqI1E5TMA.xml", "PwC Insights"),
    ("https://rss.app/feeds/9Z3q3nfx7PhpuUhE.xml", "Roland Berger"),
    # Presse Business
    ("https://www.businessinsider.com/rss", "Business Insider"),
    ("https://rss.app/feeds/BJ580weB9yIHzJ6k.xml", "Forbes"),
    # Grands acteurs IA & Presse Tech généraliste
    ("https://blog.google/technology/ai/rss/", "Google AI Blog"),
    ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "The Verge AI"),
    ("https://arstechnica.com/ai/feed/", "Ars Technica AI"),
    ("https://www.wired.com/feed/tag/ai/latest/rss", "Wired AI"),
    # Reuters AI retiré : RSS bloqué (0 articles)
    # Presse Tech
    ("https://aithority.com/feed/", "AIthority"),
    ("https://www.cio.com/feed/", "CIO.com"),
    ("https://nvidianews.nvidia.com/rss.xml", "NVIDIA Newsroom"),
    ("https://rss.app/feeds/bdaGMyWkTwKKsATN.xml", "Meta AI"),
    ("https://media.rss.com/ai-news-chatgpt-openai-anthropic-claude/feed.xml", "AI News Podcast"),
]

SEED_CATEGORIES = [
    (
        "Actualité IA",
        "#3b82f6",
        "Annonces, lancements, mouvements stratégiques dans l'industrie IA ayant une résonance pour les grandes entreprises françaises et européennes. Inclut les sorties de nouveaux modèles majeurs (GPT, Gemini, Mistral, Llama, Claude...), les partenariats stratégiques entre acteurs technologiques et industriels, les acquisitions et consolidations du marché, et les positionnements des grands acteurs français de l'IA (Mistral, Hugging Face, Thales, Capgemini, Atos...). Les résumés doivent répondre à la question : \"Qu'est-ce que cette news change pour une grande entreprise française ?\"",
        1,
    ),
    (
        "Innovation & Hype IA",
        "#8b5cf6",
        "Avancées technologiques majeures et tendances de fond qui vont redéfinir les pratiques dans les grandes organisations dans les 12 à 36 prochains mois. Inclut les agents autonomes, l'IA multimodale, les LLMs spécialisés métier, le raisonnement avancé, la GenAI appliquée aux processus d'entreprise, et les signaux faibles à surveiller. IMPORTANT : écarter la spéculation pure sur l'AGI ou la superintelligence — privilégier les innovations avec une trajectoire d'application concrète en entreprise. Les résumés doivent répondre à : \"Pourquoi un directeur de Lab IA doit-il surveiller cette tendance ?\"",
        2,
    ),
    (
        "Éthique & Réglementaire",
        "#ec4899",
        "Tout ce qui concerne le cadre légal et éthique de l'IA en France et en Europe, avec un impact direct sur les obligations des grandes entreprises. Priorité absolue à : l'AI Act européen et son calendrier d'application, la CNIL et ses recommandations sur l'IA, la propriété intellectuelle des contenus générés par IA, la responsabilité des systèmes IA en entreprise, la conformité des outils IA déployés (données personnelles, biais, auditabilité), et les prises de position des régulateurs français (AMF, ANSSI, DINUM). Les résumés doivent répondre à : \"Qu'est-ce que notre entreprise doit surveiller ou anticiper sur le plan légal et éthique ?\"",
        3,
    ),
    (
        "RH & Impacts Sociaux",
        "#f59e0b",
        "Impact de l'IA sur les métiers, les compétences et le collectif de travail dans les grandes entreprises françaises. Inclut : transformation des métiers par fonction (finance, RH, juridique, commercial, IT...), programmes de formation et montée en compétences IA, négociations sociales autour de l'automatisation, adoption des outils IA par les collaborateurs et facteurs de résistance, nouvelles organisations du travail homme-machine, et études sur le vécu des salariés face à l'IA. IMPORTANT : le contexte social français est spécifique (dialogue social fort, rôle des IRP, cadre légal du travail). Les résumés doivent répondre à : \"Comment nos collaborateurs et nos managers sont-ils concernés par ce sujet ?\"",
        4,
    ),
    (
        "Cas d'Usages & Retours Marché",
        "#10b981",
        "Déploiements concrets de l'IA dans des organisations comparables — grandes entreprises françaises et européennes en priorité, ou multinationales avec des enseignements transposables. Inclut : retours d'expérience chiffrés (gains de productivité, ROI, délais de déploiement), cas d'usage sectoriels (banque-assurance, industrie, retail, énergie, télécoms, secteur public...), comparatifs d'outils enterprise (Microsoft Copilot, Google Workspace AI, Salesforce Einstein, ServiceNow AI...), gouvernance et organisation des Lab IA internes, et rapports de référence (McKinsey, BCG, Gartner, IDC, France Stratégie) sur la maturité IA des grandes organisations. Les résumés doivent répondre à : \"Qu'est-ce qu'on peut apprendre et potentiellement reproduire dans notre entreprise ?\"",
        5,
    ),
]


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                last_fetched TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '#6b7280',
                description TEXT DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_id INTEGER NOT NULL,
                url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                published_at TEXT,
                fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
                is_ai_related INTEGER DEFAULT 0,
                title_fr TEXT,
                summary_fr TEXT,
                category_id INTEGER,
                relevance_score INTEGER DEFAULT 0,
                manually_added INTEGER DEFAULT 0,
                manually_removed INTEGER DEFAULT 0,
                user_liked INTEGER DEFAULT 0,
                FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                category_name TEXT DEFAULT '',
                reason TEXT DEFAULT 'rejected',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

        # Migration: add title_fr column if missing
        try:
            await db.execute("ALTER TABLE articles ADD COLUMN title_fr TEXT")
            await db.commit()
        except Exception:
            pass  # column already exists

        # Migration: add user_liked column if missing
        try:
            await db.execute("ALTER TABLE articles ADD COLUMN user_liked INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass  # column already exists

        # Migration: add category_name to user_feedback if missing
        try:
            await db.execute("ALTER TABLE user_feedback ADD COLUMN category_name TEXT DEFAULT ''")
            await db.commit()
        except Exception:
            pass  # column already exists

        # Seed feeds (INSERT OR IGNORE ensures new feeds are added to existing DBs too)
        await db.executemany(
            "INSERT OR IGNORE INTO feeds (url, name) VALUES (?, ?)",
            SEED_FEEDS,
        )

        # Seed virtual feed for manually added articles
        await db.execute(
            "INSERT OR IGNORE INTO feeds (url, name, active) VALUES (?, ?, 0)",
            ("manual://", "Ajout manuel"),
        )

        # Seed categories
        cursor = await db.execute("SELECT COUNT(*) FROM categories")
        row = await cursor.fetchone()
        if row[0] == 0:
            await db.executemany(
                "INSERT OR IGNORE INTO categories (name, color, description, position) VALUES (?, ?, ?, ?)",
                SEED_CATEGORIES,
            )

        # Seed default settings
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            ("refresh_interval_hours", "4"),
        )

        await db.commit()
    finally:
        await db.close()
