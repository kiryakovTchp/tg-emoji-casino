# Deployment Instructions

This guide explains how to deploy the Telegram Emoji Casino project on a server.

## Prerequisites

Ensure your server has the following installed:
- [Docker](https://docs.docker.com/engine/install/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Git](https://git-scm.com/downloads)

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd tg-emoji-casino
   ```

2. **Configure Environment Variables:**
   Copy the example environment file (if available) or create a `.env` file in the root directory.
   ```bash
   cp .env.example .env  # If .env.example exists
   # OR
   nano .env
   ```
   Ensure the following variables are set in `.env`:
   ```env
   POSTGRES_PASSWORD=your_secure_password
   DATABASE_URL_DOCKER=postgresql+asyncpg://postgres:your_secure_password@postgres:5432/casino
   REDIS_URL_DOCKER=redis://redis:6379/0
   # Add other necessary variables from your local .env
   ```

## Running the Application

You can use the provided `Makefile` or `docker-compose` directly.

### Option 1: Using Makefile (Recommended)

To build and start the services:
```bash
make up
```

To run database migrations:
```bash
make migrate
```

### Option 2: Using Docker Compose

To build and start the services in detached mode (background):
```bash
docker compose up -d --build
```

To run database migrations:
```bash
docker compose run --rm bot alembic upgrade head
```

## Verifying Deployment

Check the status of the containers:
```bash
docker compose ps
```

View logs if needed:
```bash
docker compose logs -f
```

The application should now be running.
- Bot API: `http://localhost:8000` (or server IP)
- Crash Web: `http://localhost:3000` (or server IP)
