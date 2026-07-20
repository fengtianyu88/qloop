# qloop

> English | [简体中文](README_zh-CN.md)

> Version: 1.2.0  Date: 2026-07-18

## About the Name

**qloop** = **Q**uality + **Loop**. It fuses "quality" and "closed loop" into one, alluding to testing that continuously cycles and refines throughout development without leaving gaps. Five letters, extremely short, abstract and modern.

## Overview

qloop is a quality closed-loop management system that governs the full lifecycle of code development, testing, review, and external delivery within a team. It covers code package management, review report management, test report management, LLM-based automated review, user permission management, and project lifecycle management.

## Directory Structure

```
qloop/
├── backend/                 # Backend FastAPI application
│   ├── app/
│   │   ├── api/             # API routes (auth, users, projects, releases, reviews, etc.)
│   │   ├── models/          # Database models (User, Project, Release, LLMReview, etc.)
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── services/        # Business logic layer
│   │   ├── llm/             # LLM review engine (code parsing, doc parsing, LLM calls)
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
        │   └── 2026-07-16-qloop-design.md
        └── plans/                        # Implementation plans
            └── 2026-07-16-qloop.md
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vue 3 + Element Plus + Vite + TypeScript + Pinia |
| Backend | FastAPI + SQLAlchemy 2.0 (async) + Pydantic 2 |
| Database | PostgreSQL 15+ |
| Cache / Queue | Redis 7+ |
| Object Storage | MinIO |
| Async Tasks | Celery |
| Auth | JWT (python-jose) |

## Quick Start

Read the **[Deployment Guide](docs/DEPLOYMENT.md)** for full deployment steps.

### Brief Steps

1. **Install dependencies**: PostgreSQL, Redis, MinIO
2. **Configure backend**: Copy `backend/.env.example` to `backend/.env` and fill in database address, credentials, MinIO settings, etc.
3. **Install Python dependencies**: `pip install -r backend/requirements.txt`
4. **Initialize database**: Run the table-creation script (see deployment guide)
5. **Create super admin**: Run the initialization script (see deployment guide)
6. **Start backend**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
7. **Start Celery worker**: `celery -A app.tasks.celery_app worker --loglevel=info`
8. **Build frontend**: `cd frontend && npm install && npm run build`
9. **Configure Nginx**: Serve the frontend build output and reverse-proxy `/api` to the backend

## Key Features

- **Project Management**: Project → Version → Release, a three-tier hierarchy
- **Delivery Workflow**: A 7-step release process with 3 automated LLM reviews
- **Code Package Parsing**: Supports C code, Python, MATLAB `.m` files, Simulink models, `.mat` files, `.pth` weights
- **Document Parsing**: Supports Word (`.docx`) and Excel (`.xlsx`)
- **LLM Review**: Multi-model with automatic fallback, outputs scores and recommendations. Supports any OpenAI-compatible API — minimax-M3/M2.7, GLM-5.2, Deepseek-V4-flash, Qwen, Ollama, etc.
- **Permission Management**: System-level roles (Guest / Developer / Admin / Super Admin) × Project-level roles (Project Manager / Developer / Tester / External Technical Expert)
- **Matrix Organization**: Process-domain dimension (Department → Section → Group) × Project dimension
- **Audit Logging**: Full operation audit trail
- **Notifications**: In-app notifications + email reminders
- **Self-service**: Account registration, password recovery

## Default Admin

After the first deployment, log in with:

- Username: `admin`
- Password: `Admin@123`

**Change the password immediately after login!**

## Changelog

### v1.2.0 (2026-07-18) — Production-grade SOX compliance

**P0 fixes (SOX audit traceability)**:
- Release detail page now shows uploader/trigger for each node (code package / test report / review report uploader + LLM review trigger + release confirmer)
- Fix 401 error on download buttons for code package / test report / review report (`window.open` doesn't carry token → switched to axios blob download)
- Download endpoint now writes download audit log (SOX compliance)
- Database adds 6 new `uploaded_by/uploaded_at` columns, backfilled from `audit_logs`

**Multi-LLM protocol support**:
- LLM config page adds 8 preset templates: MiniMax-M3/M2.7, GLM-5.2, DeepSeek-V4-flash (OpenAI protocol); Claude Sonnet 4.5, Claude Opus 4 (Anthropic protocol); GPT-4o, local Ollama
- Backend `LLMProtocol` enum + `client.py` already supports OpenAI/Anthropic dual-protocol calls

**Deployment script enhancement**:
- `deploy.sh` adds `run_migrations()` idempotent migration function supporting `ALTER TABLE` + historical data backfill
- Supports Ubuntu 20.04+/Debian 11+/CentOS 8+/RHEL 8+ (apt-get/dnf/yum auto-detection)

### v1.1.0 (2026-07-18)

- Initial production deployment
- Fixed 6 functional bugs (review_rules model reference, Celery worker parser, LLM score threshold, doc_parser zip support, overall_rating field, dimension_thresholds dimension names)
- One-click deployment script supports multi-LLM seeding and configurable backend address
- MiniMax-M3 review parsing fix and multi-model support

### v1.0.0 (2026-07-17)

- Initial release
- Quality 7-step release pipeline: draft → code_pending_review → test_pending_review → expert_pending_review → pending_confirm → released
- FastAPI + Vue 3 + PostgreSQL + MinIO + Redis + Celery stack
- LLM automated review, JWT auth, RBAC permissions, audit log

## License

This project is open-sourced under the [MIT License](LICENSE). Any use (including commercial) is permitted, provided the copyright notice is retained.

Copyright (c) 2026 fengtianyu88
