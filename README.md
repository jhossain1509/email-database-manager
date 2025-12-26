# Email Database Manager SaaS

A production-grade, Docker + PostgreSQL + VPS-ready email database manager with job-driven import/validate/export, RBAC roles, dashboard metrics, and US-only ccTLD import filtering.

## Features

### Core Functionality
- **Email Import**: Upload CSV/TXT files with automatic filtering and validation
- **US-only ccTLD Policy**: Allows generic TLDs (.com, .net, .org) and only .us ccTLD; blocks .gov, .edu, and all other ccTLDs
- **Job-Driven Processing**: All long-running operations use Celery workers with progress tracking
- **Email Validation**: Syntax validation, DNS/MX checks, duplicate detection, role-based filtering
- **Export & Download**: Support for verified/unverified/rejected exports with chunking
- **Reject Tracking**: All rejected emails stored with reasons; downloadable per batch

### RBAC Roles
- **Guest**: Self-registered users; can only upload/validate/download their own uploads
- **Viewer/Editor/User**: Admin-created users; can access main database according to permissions
- **Admin**: System-wide access; user management, ignore domains, download history
- **Super Admin**: Full system control including admin management

### Dashboard & Metrics
- Total Emails Uploaded/Verified/Unverified/Downloaded
- Available for Download count
- Rejected/Ignored count with reasons
- Top Domains breakdown (TOP 10 + mixed)
- Recent Jobs summary (last 5)
- Recent Activity logs

## Quick Start with Docker

### Prerequisites
- Docker and Docker Compose installed
- At least 2GB free RAM

### 1. Clone Repository
```bash
git clone https://github.com/jhossain1509/email-database-manager.git
cd email-database-manager
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env and set your SECRET_KEY
```

### 3. Build and Start Services
```bash
docker compose up -d --build
```

### 4. Initialize Database and Create Admin
```bash
docker compose exec web flask db upgrade
docker compose exec web python create_admin.py
```

### 5. Access Application
Open: `http://localhost:5000`

## Testing

Run unit tests (includes US-only ccTLD policy tests):
```bash
pytest -v
```

## VPS Deployment

See detailed deployment instructions in the full documentation above.

## Version

Current Version: 1.0.0
