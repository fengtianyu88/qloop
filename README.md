# qloop

> English | [简体中文](README_zh-CN.md)

> Version: 1.4.7  Date: 2026-07-22

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
- **Document Parsing**: Supports Word (`.docx`), Excel (`.xlsx`), ZIP archives (auto-extract + recursive parse), and plain text (`.md`, `.txt`, `.csv`, `.json`, `.yaml`)
- **LLM Review**: Multi-model with automatic fallback, outputs scores and recommendations. Supports any OpenAI-compatible API — minimax-M3/M2.7, GLM-5.2, Deepseek-V4-flash, Qwen, Ollama, etc. **Streaming output via SSE** for real-time review progress.
- **Permission Management**: System-level roles (Guest / Developer / Admin / Super Admin) × Project-level roles (Project Manager / Developer / Tester / External Technical Expert). **Auto-add dev/test/expert as project members on version creation.**
- **Matrix Organization**: Process-domain dimension (Department → Section → Group) × Project dimension
- **Audit Logging**: Full operation audit trail
- **Notifications**: In-app notifications + email reminders. **Auto-triggered at key events**: version assigned, artifact uploaded, review passed/failed, release confirmed.
- **Role-based Todo Center**: Each user sees their pending releases on the home page, filtered by role and release status.
- **Status Guidance**: Release detail page shows a "next step" banner indicating who should act and what to do next.
- **Template Download**: One-click download of code package, test report, and expert review report templates (auto-filled with project/version/user info).
- **Demo Quick Login**: Login page provides quick-login buttons for 4 demo roles (PM / Developer / Tester / Expert).
- **Self-service**: Account registration, password recovery

## Default Admin

After the first deployment, log in with:

- Username: `admin`
- Password: `admin123`

**Change the password immediately after login!**
## License

This project is open-sourced under the [MIT License](LICENSE). Any use (including commercial) is permitted, provided the copyright notice is retained.

Copyright (c) 2026 fengtianyu88
