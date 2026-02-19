import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, abort, render_template, request
from sqlmodel import Session, create_engine, select

from models import CrawlState, Indicator, Resource

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

app = Flask(__name__)


@app.template_filter("format_dt")
def format_dt(value: datetime | None) -> str:
    if value is None:
        return "jamais"
    return value.strftime("%d/%m/%Y %H:%M")


@app.route("/health")
def health():
    try:
        with Session(engine) as session:
            session.exec(select(CrawlState)).first()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}, 500


@app.route("/")
def index():
    with Session(engine) as session:
        states = {
            s.environment: s
            for s in session.exec(select(CrawlState)).all()
        }

        demo_indicators = session.exec(
            select(Indicator).where(Indicator.environment == "demo")
        ).all()
        prod_indicators = session.exec(
            select(Indicator).where(Indicator.environment == "prod")
        ).all()

        demo_slugs = {ind.slug: ind for ind in demo_indicators}
        prod_slugs = {ind.slug: ind for ind in prod_indicators}

        all_slugs = set(demo_slugs) | set(prod_slugs)
        both = sorted(s for s in all_slugs if s in demo_slugs and s in prod_slugs)
        demo_only = sorted(s for s in all_slugs if s in demo_slugs and s not in prod_slugs)
        prod_only = sorted(s for s in all_slugs if s not in demo_slugs and s in prod_slugs)

        demo_stats = _compute_stats(demo_indicators, session)
        prod_stats = _compute_stats(prod_indicators, session)

    return render_template(
        "index.html",
        states=states,
        demo_stats=demo_stats,
        prod_stats=prod_stats,
        both=both,
        demo_only=demo_only,
        prod_only=prod_only,
        demo_slugs=demo_slugs,
        prod_slugs=prod_slugs,
    )


def _compute_stats(indicators: list[Indicator], session: Session) -> dict:
    if not indicators:
        return {
            "total": 0,
            "with_viz": 0,
            "with_extras": 0,
            "total_resources": 0,
            "tabular_ok": 0,
        }
    indicator_ids = [ind.id for ind in indicators]
    resources = session.exec(
        select(Resource).where(Resource.indicator_id.in_(indicator_ids))
    ).all()
    return {
        "total": len(indicators),
        "with_viz": sum(1 for i in indicators if i.enable_visualization),
        "with_extras": sum(1 for i in indicators if i.has_ecospheres_extras),
        "total_resources": len(resources),
        "tabular_ok": sum(1 for r in resources if r.tabular_api_ok),
    }


@app.route("/indicators")
def indicators_list():
    env = request.args.get("env", "demo")
    if env not in ("demo", "prod"):
        abort(400, "env must be 'demo' or 'prod'")

    with Session(engine) as session:
        state = session.exec(
            select(CrawlState).where(CrawlState.environment == env)
        ).first()
        indicators = session.exec(
            select(Indicator).where(Indicator.environment == env)
        ).all()

        # Compute tabular ok counts per indicator
        tabular_counts: dict[int, tuple[int, int]] = {}
        for ind in indicators:
            resources = session.exec(
                select(Resource).where(Resource.indicator_id == ind.id)
            ).all()
            tabular_counts[ind.id] = (
                sum(1 for r in resources if r.tabular_api_ok),
                len(resources),
            )

    return render_template(
        "indicators/list.html",
        env=env,
        state=state,
        indicators=indicators,
        tabular_counts=tabular_counts,
    )


@app.route("/indicators/<dataset_id>")
def indicator_detail(dataset_id: str):
    env = request.args.get("env", "demo")
    if env not in ("demo", "prod"):
        abort(400, "env must be 'demo' or 'prod'")

    with Session(engine) as session:
        indicator = session.exec(
            select(Indicator).where(
                Indicator.environment == env,
                Indicator.dataset_id == dataset_id,
            )
        ).first()
        if indicator is None:
            abort(404)

        resources = session.exec(
            select(Resource).where(Resource.indicator_id == indicator.id)
        ).all()

    return render_template(
        "indicators/detail.html",
        env=env,
        indicator=indicator,
        resources=resources,
    )
