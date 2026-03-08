import anthropic
import json
import logging
import os

logger = logging.getLogger(__name__)


async def get_api_key(db) -> str | None:
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    cursor = await db.execute(
        "SELECT value FROM settings WHERE key = 'anthropic_api_key'"
    )
    row = await cursor.fetchone()
    if row and row["value"]:
        return row["value"]
    return None


async def filter_and_classify(
    articles: list[dict], categories: list[dict], api_key: str,
    rejected_examples: list[dict] | None = None,
) -> list[dict]:
    """
    Send articles to Claude in batches for AI-relevance filtering,
    classification, scoring, and French summarization.
    Returns list of classification results.
    """
    if not articles or not api_key:
        return []

    client = anthropic.AsyncAnthropic(api_key=api_key)

    categories_desc = "\n".join(
        f"- id={c['id']}: {c['name']} — {c['description']}"
        for c in categories
    )

    # Build rejected examples section
    rejected_section = ""
    if rejected_examples:
        rejected_lines = "\n".join(
            f"- \"{ex['title']}\" → score 0, is_ai_related: false"
            for ex in rejected_examples[:15]
        )
        rejected_section = f"""

ARTICLES REJETÉS PAR L'UTILISATEUR (calibre-toi sur ces exemples — des articles similaires doivent recevoir score 0) :
{rejected_lines}
"""

    system_prompt = f"""Tu es un assistant de veille IA pour le Directeur du Lab IA d'une grande entreprise française du CAC 40.
Cette veille est destinée à être diffusée à l'ensemble des collaborateurs de l'entreprise,
tous niveaux confondus : dirigeants, managers, experts métier, et employés non-techniques.

CRITÈRES D'EXCLUSION (score 0, is_ai_related = false) :
- Articles qui ne parlent PAS d'intelligence artificielle, machine learning ou automatisation intelligente
- Cybersécurité pure (ransomware, phishing, failles) SAUF si l'IA est au cœur du sujet
- Gadgets, jeux vidéo, divertissement grand public
- Sport, people, politique générale sans lien direct avec l'IA
- Recherche académique pure sans application entreprise à horizon 2 ans
- Articles listicles ("10 outils IA…") ou promotionnels sans substance
- Levées de fonds de startups mineures ou tours de financement (série A/B/C) sans portée stratégique — MAIS les levées massives ou mouvements financiers des grands acteurs IA (OpenAI, Anthropic, Google, Mistral, Meta, Microsoft, xAI, etc.) sont PERTINENTS car ils redéfinissent l'écosystème

GRILLE DE NOTATION (sois exigeant mais pas aveugle aux signaux stratégiques mondiaux) :
- Score 9-10 : Article INCONTOURNABLE — impact stratégique direct sur les grandes entreprises françaises.
  Exemples : nouvelle réglementation européenne IA, déploiement IA majeur dans une entreprise FR/EU comparable, sortie d'un modèle qui change la donne pour l'enterprise, étude de référence avec chiffres clés.
- Score 8 : Article IMPORTANT — sujet IA avec pertinence claire pour un Lab IA d'entreprise française.
  Exemples : cas d'usage chiffré transposable, tendance confirmée par plusieurs signaux, impact RH/métier documenté.
  AUSSI pertinent pour un 8 : mouvements stratégiques majeurs des grands acteurs IA (levées de fonds massives, partenariats militaires/gouvernementaux, controverses éthiques majeures, lancements de modèles de nouvelle génération) — même hors Europe, ces événements impactent l'écosystème mondial et les choix stratégiques des Lab IA.
- Score 7 : Article UTILE — lien avec l'IA en entreprise mais impact moins direct ou contexte moins français/européen.
  Inclut : news géopolitiques/stratégiques IA (régulation US, rivalités entre acteurs, usage militaire de l'IA) pertinentes pour comprendre l'environnement concurrentiel.
- Score 5-6 : Article MARGINAL — lien IA ténu, trop niche sans transposition, ou trop généraliste.
- Score 1-4 : Article HORS SUJET — pas pertinent pour cette veille.

IMPORTANT : Sois exigeant sur la qualité mais ne rejette pas les signaux stratégiques mondiaux. Un article sur une startup US inconnue sans lien avec le contexte européen ne mérite PAS un 8+. Mais une levée de $100B+ d'OpenAI ou un contrat Anthropic/Pentagone méritent un 8 car ils redéfinissent l'environnement stratégique de tout Lab IA.

EXEMPLES DE SCORING (utilise ces exemples pour calibrer tes notes) :

Exemple 1 — Score 9 :
Titre : "L'AI Act entre en application : les entreprises européennes ont 6 mois pour se conformer"
→ is_ai_related: true, score: 9, catégorie: Éthique & Réglementaire
Raison : impact réglementaire direct et immédiat sur toutes les grandes entreprises FR.

Exemple 2 — Score 8 :
Titre : "BNP Paribas déploie Copilot auprès de 10 000 collaborateurs : premiers retours"
→ is_ai_related: true, score: 8, catégorie: Cas d'Usages & Retours Marché
Raison : cas d'usage chiffré, entreprise française comparable, enseignements transposables.

Exemple 3 — Score 7 :
Titre : "Google DeepMind releases Gemini 2.5 with improved reasoning capabilities"
→ is_ai_related: true, score: 7, catégorie: Innovation & Hype IA
Raison : innovation majeure mais impact indirect, pas encore de cas d'usage entreprise concret.

Exemple 4 — Score 0 (rejeté) :
Titre : "Le PSG remporte la Ligue des Champions grâce à sa stratégie data"
→ is_ai_related: false, score: 0
Raison : article sportif, le mot "stratégie" ou "data" ne suffit pas.

Exemple 5 — Score 0 (rejeté) :
Titre : "Top 15 des meilleurs outils IA gratuits en 2025"
→ is_ai_related: false, score: 0
Raison : listicle promotionnel sans substance pour un Lab IA d'entreprise.

Exemple 6 — Score 0 (rejeté) :
Titre : "Cyberattaque massive : des hackers exploitent une faille zero-day"
→ is_ai_related: false, score: 0
Raison : cybersécurité pure sans lien avec l'IA.
{rejected_section}
CATÉGORIES — classe chaque article pertinent dans UNE seule catégorie :
{categories_desc}

Pour chaque article fourni, tu dois :
1. Déterminer si l'article est pertinent (is_ai_related: true/false)
2. Classer dans une catégorie
3. Attribuer un score selon la grille ci-dessus
4. Traduire le titre en français (title_fr). Si déjà en français, le garder tel quel.
5. Rédiger un résumé d'1 phrase courte en français (max 30 mots), orienté "ce que ça change pour une grande entreprise française"

Réponds UNIQUEMENT avec un tableau JSON valide, sans markdown, sans texte avant ou après.
Chaque élément doit avoir : url, is_ai_related, category_id, relevance_score, title_fr, summary_fr
Si l'article n'est pas pertinent, mets is_ai_related à false, category_id à null, relevance_score à 0, title_fr à null et summary_fr à null."""

    results = []

    # Process in batches of 15
    for i in range(0, len(articles), 15):
        batch = articles[i : i + 15]
        articles_text = json.dumps(
            [
                {"url": a["url"], "title": a["title"], "description": a["description"]}
                for a in batch
            ],
            ensure_ascii=False,
        )

        for attempt in range(2):  # Retry once on error
            try:
                response = await client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=8192,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": f"Analyse ces articles :\n{articles_text}"}
                    ],
                )
                text = response.content[0].text.strip()
                # Remove potential markdown fencing
                if text.startswith("```"):
                    text = text.split("\n", 1)[1]
                    if text.endswith("```"):
                        text = text[: text.rfind("```")]
                parsed = json.loads(text)
                results.extend(parsed)
                break
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error from Claude (attempt {attempt+1}): {e}")
                if attempt == 1:
                    logger.error(f"Raw response: {text[:500]}")
            except anthropic.APIError as e:
                logger.error(f"Anthropic API error (attempt {attempt+1}): {e}")
                if attempt == 1:
                    logger.error("Skipping batch after retry failure")

    return results


    # Seuils par catégorie — certaines catégories exigent un score plus élevé
CATEGORY_THRESHOLDS = {
    3: 7,   # Éthique & Réglementaire — 7+
    4: 7,   # RH & Impacts Sociaux — 7+
}
DEFAULT_THRESHOLD = 7


async def apply_classifications(db, classifications: list[dict]):
    """Apply Claude's classifications to the database with per-category thresholds."""
    for c in classifications:
        if not c.get("url"):
            continue

        is_ai = 1 if c.get("is_ai_related") else 0
        score = c.get("relevance_score", 0)
        cat_id = c.get("category_id")
        threshold = CATEGORY_THRESHOLDS.get(cat_id, DEFAULT_THRESHOLD)

        if is_ai and score >= threshold:
            await db.execute(
                """UPDATE articles SET
                   is_ai_related = 1,
                   category_id = ?,
                   relevance_score = ?,
                   title_fr = ?,
                   summary_fr = ?
                   WHERE url = ?""",
                (c.get("category_id"), score, c.get("title_fr"), c.get("summary_fr"), c["url"]),
            )
        else:
            # Mark as not AI-related (will be filtered out in queries)
            await db.execute(
                "UPDATE articles SET is_ai_related = 0, relevance_score = ? WHERE url = ?",
                (score, c["url"]),
            )

    await db.commit()


BRIEFING_TEMPLATE_PROMPT = """Tu es le rédacteur de la newsletter interne du Lab IA d'une grande entreprise française du CAC 40.
Cette veille est diffusée à l'ensemble des collaborateurs : dirigeants, managers, experts métier et employés non-techniques.

Tu DOIS respecter EXACTEMENT ce template Markdown (pas d'improvisation sur la structure) :

```
# Veille IA — [date du jour au format JJ/MM/AAAA]

**[N] articles sélectionnés**

---

## [Nom de la catégorie 1]

### [Titre de l'article en français]
[Résumé de 2-3 phrases orienté "ce que ça change pour une grande entreprise française". Court et percutant.]
Source : [Nom de la source] — [Lire l'article](url)

### [Titre de l'article suivant]
[Résumé]
Source : [Nom de la source] — [Lire l'article](url)

---

## [Nom de la catégorie 2]

...

```

RÈGLES STRICTES :
- Respecte exactement cette structure, ne rajoute PAS de sections supplémentaires
- Regroupe les articles par catégorie (utilise le champ category_name fourni)
- N'inclus QUE les catégories qui ont des articles
- Chaque article a : son titre (### en H3), un résumé court, la source (feed_name) et un lien cliquable
- Le résumé doit être en français, orienté impact entreprise, 2-3 phrases max
- Ne rajoute PAS de section de conclusion ou d'avis à la fin
- Le ton est professionnel, expert et accessible
- IMPORTANT : Génère directement le Markdown, SANS l'entourer de blocs ``` (pas de code fences)"""


async def generate_briefing(articles: list[dict], api_key: str) -> str:
    """Generate a newsletter-style briefing from selected articles."""
    client = anthropic.AsyncAnthropic(api_key=api_key)

    articles_text = json.dumps(
        [
            {
                "title": a.get("title_fr") or a["title"],
                "summary_fr": a.get("summary_fr", ""),
                "category_name": a.get("category_name", "Autre"),
                "feed_name": a.get("feed_name", ""),
                "url": a.get("url", ""),
            }
            for a in articles
        ],
        ensure_ascii=False,
    )

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=BRIEFING_TEMPLATE_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Génère la veille avec ces {len(articles)} articles :\n\n{articles_text}",
            }
        ],
    )
    return response.content[0].text


async def generate_briefing_with_prompt(
    articles: list[dict], user_prompt: str, api_key: str
) -> dict:
    """
    Claude selects the most relevant articles based on the user's custom prompt,
    then generates a briefing focused on that request.
    Returns {"briefing": str, "selected_ids": list[int]}.
    """
    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Limit to top 100 articles to stay within token limits
    articles = articles[:100]

    articles_json = json.dumps(
        [
            {
                "id": a["id"],
                "title": a.get("title_fr") or a["title"],
                "summary": (a.get("summary_fr", "") or "")[:120],
                "cat": a.get("category_name", "Autre"),
            }
            for a in articles
        ],
        ensure_ascii=False,
    )

    # Step 1: Claude selects articles
    selection_response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system="""Tu es un assistant de veille IA pour le Lab IA d'une grande entreprise française du CAC 40.
On te donne une liste d'articles et une demande utilisateur.
Tu dois sélectionner les articles les PLUS pertinents pour répondre à cette demande.
Sélectionne entre 3 et 15 articles maximum.
Réponds UNIQUEMENT avec un tableau JSON d'IDs : [1, 5, 12, ...]
Pas de markdown, pas de texte avant ou après.""",
        messages=[
            {
                "role": "user",
                "content": f"Demande : {user_prompt}\n\nArticles disponibles :\n{articles_json}",
            }
        ],
    )

    text = selection_response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    selected_ids = json.loads(text)

    # Step 2: Generate briefing with selected articles + custom angle
    selected = [a for a in articles if a["id"] in selected_ids]
    if not selected:
        selected = articles[:10]  # fallback

    articles_text = json.dumps(
        [
            {
                "title": a.get("title_fr") or a["title"],
                "summary_fr": a.get("summary_fr", ""),
                "category_name": a.get("category_name", "Autre"),
                "feed_name": a.get("feed_name", ""),
                "url": a.get("url", ""),
            }
            for a in selected
        ],
        ensure_ascii=False,
    )

    prompt_instruction = BRIEFING_TEMPLATE_PROMPT + f"""

CONTEXTE SUPPLÉMENTAIRE : L'utilisateur a fait une demande spécifique : "{user_prompt}"
Oriente les résumés selon cet angle, tout en respectant le template."""

    briefing_response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=prompt_instruction,
        messages=[
            {
                "role": "user",
                "content": f"Génère la veille avec ces {len(selected)} articles :\n\n{articles_text}",
            }
        ],
    )

    return {
        "briefing": briefing_response.content[0].text,
        "selected_ids": selected_ids,
    }
