import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import markdown
from flask import Flask, abort, g, render_template, request
from sqlmodel import Session, create_engine, select

from models import CrawlState, Indicator, Resource

DATABASE_URL = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)

INDICATORS_DOC_PATH = Path(__file__).parent / "INDICATORS.md"

app = Flask(__name__)


def get_session() -> Session:
    if "session" not in g:
        g.session = Session(engine)
    return g.session


@app.teardown_appcontext
def close_session(exception: BaseException | None = None) -> None:
    session = g.pop("session", None)
    if session is not None:
        session.close()


@app.template_filter("format_filesize")
def format_filesize(value: int | None) -> str:
    if value is None:
        return "—"
    for unit in ("o", "Ko", "Mo", "Go"):
        if value < 1024:
            return f"{value:.0f} {unit}"
        value /= 1024
    return f"{value:.1f} To"


@app.template_filter("format_dt")
def format_dt(value: datetime | None) -> str:
    if value is None:
        return "jamais"
    return value.strftime("%d/%m/%Y %H:%M")


@app.route("/health")
def health():
    try:
        get_session().exec(select(CrawlState)).first()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}, 500


@app.route("/")
def index():
    session = get_session()
    states = {s.environment: s for s in session.exec(select(CrawlState)).all()}
    demo_stats = _compute_stats("demo", session)
    prod_stats = _compute_stats("prod", session)

    return render_template(
        "index.html",
        states=states,
        demo_stats=demo_stats,
        prod_stats=prod_stats,
    )


def _compute_stats(env: str, session: Session) -> dict:
    indicators = session.exec(select(Indicator).where(Indicator.environment == env)).all()
    if not indicators:
        return {"total": 0, "with_viz": 0, "with_extras": 0, "total_resources": 0, "tabular_ok": 0}
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

    session = get_session()
    state = session.exec(select(CrawlState).where(CrawlState.environment == env)).first()
    indicators = session.exec(select(Indicator).where(Indicator.environment == env)).all()

    indicator_ids = [ind.id for ind in indicators]
    all_resources = session.exec(select(Resource).where(Resource.indicator_id.in_(indicator_ids))).all()
    resources_by_indicator: dict[int, list[Resource]] = {}
    for r in all_resources:
        resources_by_indicator.setdefault(r.indicator_id, []).append(r)

    tabular_counts: dict[int, tuple[int, int]] = {}
    for ind in indicators:
        rs = resources_by_indicator.get(ind.id, [])
        tabular_counts[ind.id] = (sum(1 for r in rs if r.tabular_api_ok), len(rs))

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

    session = get_session()
    indicator = session.exec(
        select(Indicator).where(
            Indicator.environment == env,
            Indicator.dataset_id == dataset_id,
        )
    ).first()
    if indicator is None:
        abort(404)

    resources = session.exec(select(Resource).where(Resource.indicator_id == indicator.id)).all()

    return render_template(
        "indicators/detail.html",
        env=env,
        indicator=indicator,
        resources=resources,
    )


@app.route("/doc")
def doc():
    content = INDICATORS_DOC_PATH.read_text()
    doc_html = markdown.markdown(content, extensions=["tables", "fenced_code"])
    return render_template("doc.html", doc_html=doc_html)
