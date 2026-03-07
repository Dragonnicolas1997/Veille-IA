# Veille IA — RSS AI Intelligence Monitor

Full-stack application that monitors RSS feeds, filters AI-relevant articles using Claude, and presents them classified and summarized in French.

## Stack

- **Backend:** Python + FastAPI + SQLite (aiosqlite) + APScheduler
- **Frontend:** React + Vite
- **AI:** Anthropic Claude Haiku 4.5 for article classification

## Setup & Run

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend runs on http://localhost:8000. API docs at http://localhost:8000/docs.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on http://localhost:5173.

## Configuration

1. Start both backend and frontend
2. Open http://localhost:5173
3. In **Settings**, enter your Anthropic API key
4. Click **Refresh Feeds** to fetch articles and run Claude classification

## Features

- RSS feed management (add/remove feeds)
- Automatic feed refresh via APScheduler (configurable interval)
- AI-powered article filtering and classification via Claude
- French summaries with relevance scoring (1-10)
- Category management with color coding
- Article filtering by category

## Default Feeds

- MIT Tech Review
- The Verge AI
- VentureBeat AI
- Hacker News
- Microsoft AI Blog

## Default Categories

- LLMs & Modèles
- IA Générative
- IA en Entreprise
- Régulation & Éthique
- Recherche & Innovation

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| GET | /api/feeds | List all feeds |
| POST | /api/feeds | Add feed |
| DELETE | /api/feeds/{id} | Remove feed |
| POST | /api/feeds/refresh | Manual refresh + classification |
| GET | /api/articles | List articles (with filters) |
| PATCH | /api/articles/{id} | Update article |
| GET | /api/categories | List categories |
| POST | /api/categories | Create category |
| PUT | /api/categories/{id} | Update category |
| DELETE | /api/categories/{id} | Delete category |
| GET | /api/settings | Get settings |
| PUT | /api/settings | Update settings |
| GET | /api/stats | Dashboard stats |
