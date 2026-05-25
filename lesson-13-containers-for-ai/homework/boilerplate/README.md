# Lesson 13 — RAG App Containerization

Контейнеризація FastAPI RAG-застосунку: порівняння naive vs multi-stage білду + повний compose-стек з Qdrant, Redis, Langfuse.

## Структура

- `Dockerfile.naive` — baseline (повний `python:3.11`, без оптимізацій)
- `Dockerfile` — production: multi-stage, slim, non-root, healthcheck
- `docker-compose.yml` — app + Qdrant + Redis + Langfuse (+ Postgres для Langfuse)
- `.dockerignore` — виключає `.venv`, `__pycache__`, `.env`, тести

## Як запустити

```bash
# 1. Заповнити секрети
cp .env.example .env
# відредагувати .env: OPENAI_API_KEY + секрети для Langfuse
echo "LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -hex 32)" >> .env
echo "LANGFUSE_SALT=$(openssl rand -hex 16)" >> .env

# 2. Підняти стек
docker compose up -d --build

# 3. Перевірити
docker compose ps
curl localhost:8000/health
curl -X POST localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What is RAG?"}'

# Langfuse UI: http://localhost:3000
# Qdrant UI:   http://localhost:6333/dashboard
```

## Метрики: Naive vs Multi-stage

| Метрика                          | Naive          | Multi-stage    | Виграш |
|----------------------------------|----------------|----------------|--------|
| Image size                       | 1750 MB        | 368 MB         | MS     |
| Build time (cold, без cache)     | 15.196 s       | 24.805 s       | Naive  |
| Rebuild after code change        | 14.854 s       | 1.905 s        | MS     |
| Cold start (до `/health=ok`)     | 1 s            | 2 s            | Naive  |
| Vulnerabilities (Docker Scout)   | 4C/22H/24M/183L| 0C/1H/4M/22L   | MS     |

### Як заміряти

**Image size:**
```bash
docker build --no-cache -f Dockerfile.naive -t rag-naive .
docker build --no-cache -f Dockerfile        -t rag-optimized .
docker images | grep -E "rag-(naive|optimized)"
```

**Build time (cold):**
```bash
docker builder prune -af
time docker build -f Dockerfile.naive -t rag-naive .
docker builder prune -af
time docker build -f Dockerfile        -t rag-optimized .
```

**Rebuild after code change** (ключова метрика — показує силу layer caching):
```bash
# Зміни щось у app/main.py, наприклад додай коментар
echo "# touch" >> app/main.py

time docker build -f Dockerfile.naive -t rag-naive .
time docker build -f Dockerfile        -t rag-optimized .
```

**Cold start** (час від `docker run` до `/health` повертає `{"status":"ok"}`):
```bash
# Для кожного образу:
docker run -d --name rag-test -p 8000:8000 --env-file .env <image>
time until curl -fs localhost:8000/health | grep -q '"ok"'; do sleep 0.1; done
docker rm -f rag-test
```

**Vulnerabilities:**
```bash
docker scout cves rag-naive
docker scout cves rag-optimized
```

## Чому multi-stage виграє

1. **База `slim-bookworm` замість повного `python:3.11`** — ~120 MB vs ~1 GB. Повний образ тягне `gcc`, `git`, документацію, мови — нічого з цього у runtime не треба.
2. **Builder stage не потрапляє у фінальний образ** — pip-кеш, build-toolchain, тимчасові артефакти лишаються в проміжному шарі і відкидаються.
3. **`requirements.txt` копіюється перед кодом** — `pip install` шар кешується. Зміна `app/main.py` не інвалідує його → rebuild за секунди замість хвилин.
4. **Non-root user** — `app` юзер замість `root` обмежує blast radius у разі RCE.
5. **HEALTHCHECK** — оркестратор (compose, k8s) бачить реальний стан застосунку, не тільки факт що процес живий.
6. **`apt-get upgrade` + `pip install --upgrade setuptools wheel`** — підтягує security-патчі.

## Скріншоти

- `screenshots/docker-images.png` — `docker images` з обома образами
- `screenshots/curl-ask.png` — відповідь `/ask` з RAG-відповіддю
- `screenshots/compose-ps.png` — `docker compose ps` зі всіма healthy сервісами
