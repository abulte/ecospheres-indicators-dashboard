import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator
from sqlmodel import Session, or_, select

from models import CrawlState, Indicator, Resource

logger = logging.getLogger(__name__)

_EXTRAS_SCHEMA = json.loads(Path(__file__).parent.joinpath("extras_schema.json").read_text())
_EXTRAS_VALIDATOR = Draft202012Validator(_EXTRAS_SCHEMA)

_RESOURCE_EXTRAS_SCHEMA = json.loads(Path(__file__).parent.joinpath("resource_extras_schema.json").read_text())
_RESOURCE_EXTRAS_VALIDATOR = Draft202012Validator(_RESOURCE_EXTRAS_SCHEMA)

_CORS_ORIGIN = "https://ecologie.data.gouv.fr"

ENVIRONMENTS = {
    "demo": {
        "base_url": "https://demo.data.gouv.fr",
        "tabular_api_url": "https://tabular-api.preprod.data.gouv.fr",
        "org_id": os.getenv("DATAGOUV_ORG_ID_DEMO"),
    },
    "prod": {
        "base_url": "https://www.data.gouv.fr",
        "tabular_api_url": "https://tabular-api.data.gouv.fr",
        "org_id": os.getenv("DATAGOUV_ORG_ID_PROD"),
    },
}


def _check(name: str, ok: bool, detail: Any = None) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def fetch_dataset(client: httpx.Client, base_url: str, id_or_slug: str) -> dict:
    resp = client.get(f"{base_url}/api/2/datasets/{id_or_slug}/")
    resp.raise_for_status()
    return resp.json()


def fetch_all_indicators(client: httpx.Client, base_url: str, org_id: str | None) -> list[dict]:
    datasets = []
    page = 1
    while True:
        params = {"tag": "ecospheres-indicateurs", "page_size": 100, "page": page}
        if org_id:
            params["organization"] = org_id
        resp = client.get(f"{base_url}/api/2/datasets/search/", params=params)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("data", [])
        datasets.extend(results)
        if len(datasets) >= data.get("total", 0):
            break
        page += 1
    return datasets


def fetch_resources(client: httpx.Client, base_url: str, dataset_id: str, resource_type: str = "main") -> list[dict]:
    resources = []
    page = 1
    while True:
        resp = client.get(
            f"{base_url}/api/2/datasets/{dataset_id}/resources/",
            params={"page_size": 100, "page": page, "type": resource_type},
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("data", [])
        resources.extend(results)
        if len(resources) >= data.get("total", 0):
            break
        page += 1
    return resources


def check_extras(dataset_id: str, extras: dict) -> tuple[bool, bool, list[dict]]:
    """Validate dataset extras. Returns (has_ecospheres_extras, enable_visualization, checks)."""
    # Always try to read enable_visualization regardless of schema validity
    ind_extras = extras.get("ecospheres-indicateurs", {})
    enable_visualization = bool(ind_extras.get("enable_visualization", False))

    raw_errors = list(_EXTRAS_VALIDATOR.iter_errors(extras))
    if raw_errors:
        errors = [
            {"path": e.json_path if e.json_path != "$" else "(root)", "message": e.message}
            for e in raw_errors
        ]
        logger.warning("Extras schema violations for dataset %s (%d error(s)):", dataset_id, len(errors))
        for err in errors:
            logger.warning("  %s: %s", err["path"], err["message"])
        return False, enable_visualization, [_check("extras_schema", ok=False, detail=errors)]

    return True, enable_visualization, [_check("extras_schema", ok=True)]


def check_resource_extras(resource_id: str, extras: dict) -> dict:
    """Validate resource extras against the schema. Returns a single check dict."""
    raw_errors = list(_RESOURCE_EXTRAS_VALIDATOR.iter_errors(extras))
    if raw_errors:
        errors = [
            {"path": e.json_path if e.json_path != "$" else "(root)", "message": e.message}
            for e in raw_errors
        ]
        logger.warning("Resource extras schema violations for %s (%d error(s)):", resource_id, len(errors))
        for err in errors:
            logger.warning("  %s: %s", err["path"], err["message"])
        return _check("resource_extras_schema", ok=False, detail=errors)
    return _check("resource_extras_schema", ok=True)


def check_tabular_api(client: httpx.Client, tabular_api_url: str, resource_id: str) -> tuple[str, list[dict], bool]:
    """Run tabular API checks. Returns (url, checks, overall_ok)."""
    url = f"{tabular_api_url}/api/resources/{resource_id}/data/?page_size=1"
    checks = []
    try:
        resp = client.get(url, headers={"Origin": _CORS_ORIGIN}, follow_redirects=True)
        status = resp.status_code
        http_ok = resp.is_success
        checks.append(_check("tabular_api_http", ok=http_ok, detail=status))

        acao = resp.headers.get("Access-Control-Allow-Origin", "")
        cors_ok = acao == "*" or acao == _CORS_ORIGIN
        checks.append(_check("tabular_api_cors", ok=cors_ok, detail=acao or None))
    except httpx.RequestError as e:
        checks.append(_check("tabular_api_http", ok=False, detail=str(e)))
        checks.append(_check("tabular_api_cors", ok=False, detail=None))

    overall_ok = all(c["ok"] for c in checks)
    return url, checks, overall_ok


def _crawl_dataset(
    client: httpx.Client,
    base_url: str,
    tabular_api_url: str,
    env: str,
    ds: dict,
    session: Session,
) -> None:
    """Crawl a single dataset dict and upsert its Indicator + Resources."""
    dataset_id = ds["id"]
    extras = ds.get("extras", {})
    has_ecospheres_extras, enable_visualization, indicator_checks = check_extras(dataset_id, extras)

    indicator = Indicator(
        environment=env,
        dataset_id=dataset_id,
        title=ds.get("title", ""),
        slug=ds.get("slug", ""),
        enable_visualization=enable_visualization,
        has_ecospheres_extras=has_ecospheres_extras,
        checks=indicator_checks,
        resource_count=0,
    )
    session.add(indicator)
    session.flush()

    try:
        raw_resources = fetch_resources(client, base_url, dataset_id)
    except httpx.HTTPError as e:
        logger.warning("[%s] Could not fetch resources for %s: %s", env, dataset_id, e)
        raw_resources = []

    for raw in raw_resources:
        resource_id = raw["id"]
        resource_extras = raw.get("extras", {})
        extras_check = check_resource_extras(resource_id, resource_extras)
        tab_url, resource_checks, tab_ok = check_tabular_api(client, tabular_api_url, resource_id)
        resource_checks = [extras_check] + resource_checks
        session.add(Resource(
            indicator_id=indicator.id,
            resource_id=resource_id,
            title=raw.get("title", ""),
            url=raw.get("url"),
            format=raw.get("format"),
            filetype=raw.get("filetype"),
            resource_type=raw.get("type"),
            tabular_api_url=tab_url,
            checks=resource_checks,
            tabular_api_ok=tab_ok,
        ))

    indicator.resource_count = len(raw_resources)
    session.commit()

    tabular_ok_count = sum(1 for r in indicator.resources if r.tabular_api_ok)
    logger.info(
        "[%s] %s: %d resource(s), tabular ok: %d/%d",
        env, dataset_id, len(raw_resources), tabular_ok_count, len(raw_resources),
    )


def crawl_environment(env: str, session: Session) -> None:
    config = ENVIRONMENTS[env]
    base_url = config["base_url"]
    tabular_api_url = config["tabular_api_url"]
    org_id = config["org_id"]

    state = session.exec(select(CrawlState).where(CrawlState.environment == env)).first()
    if state is None:
        state = CrawlState(environment=env)
        session.add(state)

    state.status = "running"
    state.started_at = datetime.now(timezone.utc)
    state.completed_at = None
    state.error = None
    state.indicator_count = None
    session.commit()

    try:
        logger.info("[%s] Deleting existing indicators", env)
        for ind in session.exec(select(Indicator).where(Indicator.environment == env)).all():
            session.delete(ind)
        session.commit()

        with httpx.Client(timeout=30) as client:
            logger.info("[%s] Fetching indicators from %s", env, base_url)
            datasets = fetch_all_indicators(client, base_url, org_id)
            logger.info("[%s] Found %d indicators", env, len(datasets))

            for ds in datasets:
                _crawl_dataset(client, base_url, tabular_api_url, env, ds, session)

        state.status = "completed"
        state.completed_at = datetime.now(timezone.utc)
        state.indicator_count = len(datasets)
        session.commit()
        logger.info("[%s] Crawl completed: %d indicators", env, len(datasets))

    except Exception as e:
        state.status = "failed"
        state.completed_at = datetime.now(timezone.utc)
        state.error = str(e)
        session.commit()
        logger.exception("[%s] Crawl failed", env)
        raise


def crawl_indicator(env: str, id_or_slug: str, session: Session) -> None:
    config = ENVIRONMENTS[env]
    base_url = config["base_url"]
    tabular_api_url = config["tabular_api_url"]

    with httpx.Client(timeout=30) as client:
        logger.info("[%s] Fetching dataset %s", env, id_or_slug)
        ds = fetch_dataset(client, base_url, id_or_slug)
        dataset_id = ds["id"]

        existing = session.exec(
            select(Indicator).where(
                Indicator.environment == env,
                or_(Indicator.dataset_id == dataset_id, Indicator.slug == id_or_slug),
            )
        ).first()
        if existing:
            logger.info("[%s] Deleting existing indicator %s", env, existing.dataset_id)
            session.delete(existing)
            session.commit()

        _crawl_dataset(client, base_url, tabular_api_url, env, ds, session)
