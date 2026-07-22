# qloop

> The quality closed loop that ships with confidence.

[![Version](https://img.shields.io/badge/version-1.4.7-blue.svg)](./README.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/vue-3-4FC08D.svg)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688.svg)](https://fastapi.tiangolo.com/)

> English | [简体中文](README_zh-CN.md)

---

## Why qloop?

Releasing software in a team is rarely just "merge and ship." It is a chain of
hand-offs: code review → test report → expert review → PM approval → release.
Each hand-off is a place where things silently go wrong.

**Existing tools force you to stitch together a wiki, a chat group, a shared
drive, and a home-grown review script.** Context is lost at every boundary,
status is unclear, and nobody knows who should act next.

**qloop closes that loop.** It unifies the entire release pipeline — artifacts,
reviews, approvals, notifications — into one system with a single source of
truth, and brings LLM-powered automated review to every gate.

| Pain without qloop | What qloop changes |
|---|---|
| "Where is the latest code package?" | Every artifact is versioned and stored in MinIO, downloadable by role. |
| "Did the review pass?" | LLM reviews run automatically at each gate, with scores and suggestions. |
| "Who should act next?" | A status banner tells each user exactly what to do next. |
| "Why was this released?" | Full audit trail + notification feed for every release event. |
| "Re-reviewing the same code by hand." | Multi-model LLM review with streaming output and automatic fallback. |

---

## Core Features

### Release Pipeline
- **Project → Version → Release** three-tier hierarchy
- **7-step release workflow** with 3 automated LLM review gates (code / test report / expert report)
- **Status guidance**: each release detail page shows a "next step" banner — who should act, what to do
- **Role-based todo center**: every user sees their own pending releases on the home page

### LLM-Powered Review
- **Streaming output via SSE**: watch the LLM think in real time — step events (file read, LLM connected) and token-by-token stream in the progress panel
- **Multi-model with automatic fallback**: primary model fails → fallback model takes over
- **Any OpenAI-compatible backend**: minimax-M3/M2.7, GLM-5.2, Deepseek-V4-flash, Qwen, Ollama, vLLM, TGI — all work out of the box
- **Structured JSON output**: scores per dimension, total score, conclusion, and improvement suggestions

### Artifact Parsing
- **Code packages**: C, Python, MATLAB `.m`, Simulink models, `.mat` data, `.pth` weights
- **Documents**: Word (`.docx`), Excel (`.xlsx`), plain text (`.md`/`.txt`/`.csv`/`.json`/`.yaml`)
- **ZIP archives**: auto-extract + recursive parse of nested archives
- **Templates**: one-click download of code/test/expert-report templates, auto-filled with project & version info

### Permissions & Organization
- **System roles**: Guest / Developer / Admin / Super Admin
- **Project roles**: Project Manager / Developer / Tester / External Technical Expert
- **Auto-membership**: creating a version auto-adds the assigned dev/test/expert as project members
- **Matrix organization**: process-domain dimension (Department → Section → Group) × project dimension
- **Full audit logging** of every operation

### Notifications
- **In-app notifications + email reminders**
- **Auto-triggered at key events**: version assigned, artifact uploaded, review passed/failed, release confirmed
- **Notification dedup** (v1.4.7): SSE reconnects no longer replay already-shown notifications

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Browser (Vue 3 SPA)                       │
│  Element Plus · Pinia · Vite · TypeScript · SSE EventSource      │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTPS / SSE
┌──────────────────────────────▼───────────────────────────────────┐
│                     Nginx (reverse proxy)                         │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│                     FastAPI (async, JWT auth)                     │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │ API Routes  │  │  Services    │  │  LLM Review Engine      │   │
│  │ auth/users/ │  │  audit ·     │  │  code_parser ·          │   │
│  │ projects/   │  │  permission  │  │  doc_parser ·           │   │
│  │ releases/   │  │  release     │  │  client (streaming) ·   │   │
│  │ reviews     │  │  notification│  │  reviewer               │   │
│  └─────────────┘  └──────────────┘  └────────────────────────┘   │
└───────┬──────────────────┬───────────────────┬───────────────────┘
        │                  │                   │
   ┌────▼─────┐      ┌─────▼─────┐       ┌─────▼──────┐
   │PostgreSQL│      │   Redis   │       │   MinIO    │
   │  15+     │      │ cache +   │       │ artifacts  │
   │ metadata │      │  pub/sub  │       │ (code/     │
   │ audit    │      │  channel  │       │  reports)  │
   └──────────┘      └─────┬─────┘       └────────────┘
                           │
                  ┌────────▼─────────┐
                  │  Celery worker   │
                  │  · LLM review    │
                  │  · email         │
                  │  · notifications  │
                  └────────┬─────────┘
                           │ progress_callback
                           │ → Redis publish
                           │ → SSE endpoint
                           │ → browser stream
                           ▼
                  ┌──────────────────┐
                  │  LLM Backend     │
                  │  (OpenAI-compat) │
                  └──────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vue 3 · Element Plus · Vite · TypeScript · Pinia |
| Backend | FastAPI · SQLAlchemy 2.0 (async) · Pydantic 2 |
| Database | PostgreSQL 15+ |
| Cache / Queue | Redis 7+ (cache + pub/sub for SSE) |
| Object Storage | MinIO |
| Async Tasks | Celery |
| LLM Review | httpx async streaming · any OpenAI-compatible API |
| Auth | JWT (python-jose) |

---

## Quick Start

Read the **[Deployment Guide](docs/DEPLOYMENT.md)** for full steps (Linux + Windows).

### Brief Steps

1. **Install dependencies**: PostgreSQL, Redis, MinIO
2. **Configure backend**: copy `backend/.env.example` → `backend/.env`, fill in DB / Redis / MinIO / LLM settings
3. **Install Python deps**: `pip install -r backend/requirements.txt`
4. **Initialize database**: run the table-creation script (see deployment guide)
5. **Create super admin**: run the init script (see deployment guide)
6. **Start backend**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
7. **Start Celery worker**: `celery -A app.tasks.celery_app worker --loglevel=info`
8. **Build frontend**: `cd frontend && npm install && npm run build`
9. **Configure Nginx**: serve the frontend build and reverse-proxy `/api` → backend

---

## Directory Structure

```
qloop/
├── backend/                 # Backend FastAPI application
│   ├── app/
│   │   ├── api/             # API routes (auth, users, projects, releases, reviews)
│   │   ├── models/          # Database models (User, Project, Release, LLMReview, ...)
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── services/        # Business logic (audit, permission, release, ...)
│   │   ├── llm/             # LLM review engine (code_parser, doc_parser, client, reviewer)
│   │   ├── tasks/           # Celery async tasks (LLM review, email, notifications)
│   │   ├── storage/         # MinIO file storage
│   │   ├── utils/           # Utilities (security, pagination)
│   │   ├── config.py        # Configuration management
│   │   ├── database.py      # Database connection
│   │   └── main.py          # Application entry point
│   ├── .env.example         # Environment variable template
│   └── requirements.txt     # Python dependencies
├── frontend/                # Frontend Vue 3 application
│   ├── src/
│   │   ├── api/             # API request modules
│   │   ├── components/      # Shared components (Layout)
│   │   ├── router/          # Routing configuration
│   │   ├── stores/          # Pinia state management
│   │   ├── types/           # TypeScript type definitions
│   │   ├── views/           # Page components
│   │   ├── App.vue          # Root component
│   │   └── main.ts          # Application entry point
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
└── docs/                    # Documentation
    ├── DEPLOYMENT.md                     # Deployment guide (Linux + Windows)
    └── superpowers/
        ├── specs/                        # Design documents
        └── plans/                        # Implementation plans
```

---

## Documentation

- **[Deployment Guide](docs/DEPLOYMENT.md)** — full deployment steps for Linux & Windows
- **[Design Document v1.4.7](docs/superpowers/specs/2026-07-22-qloop-design-v1.4.7.md)** — incremental design notes covering v1.4.0 → v1.4.7

---

## Default Admin

After the first deployment, log in with:

- Username: `admin`
- Password: `admin123`

**Change the password immediately after first login!**

---

## About the Name

**qloop** = **Q**uality + **Loop**. It fuses "quality" and "closed loop" into
one — testing that continuously cycles and refines throughout development
without leaving gaps. Five letters, short, abstract, modern.

---

## License

This project is open-sourced under the [MIT License](LICENSE). Any use
(including commercial) is permitted, provided the copyright notice is retained.

Copyright (c) 2026 fengtianyu88


---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=fengtianyu88/qloop&type=Date)](https://star-history.com/#fengtianyu88/qloop&Date)
