# Ecosphères Indicators Dashboard

Monitoring dashboard for the publication and crawling state of [Ecosphères](https://ecologie.data.gouv.fr) indicators on `demo.data.gouv.fr` and `www.data.gouv.fr`.

## Stack

Flask · SQLModel · PostgreSQL · httpx · Alembic · minicli · SimpleCSS

## Setup

```bash
# Start the database
docker compose up -d

# Install dependencies
uv sync

# Run migrations
uv run alembic upgrade head
```

## Crawling

```bash
uv run python cli.py crawl demo       # crawl demo environment
uv run python cli.py crawl prod       # crawl prod environment
uv run python cli.py crawl all        # crawl both

# Recrawl a single indicator by dataset ID or slug
uv run python cli.py crawl demo --dataset <id_or_slug>
```

## Running the app

```bash
uv run flask run
```

Open [http://localhost:5000](http://localhost:5000).

## What it checks

For each indicator (dataset tagged `ecospheres-indicateurs`):

- **Extras schema** — validates `extras["ecospheres-indicateurs"]` against `extras_schema.json`

For each `main` resource of each indicator:

- **Resource extras schema** — validates `extras["ecospheres-indicateurs"]` against `resource_extras_schema.json`
- **Tabular API HTTP** — `GET {tabular_api_url}/api/resources/{id}/data/?page_size=1`
- **Tabular API CORS** — checks `Access-Control-Allow-Origin` allows `https://ecologie.data.gouv.fr`
