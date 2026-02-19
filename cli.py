import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from minicli import cli, run
from sqlmodel import Session, create_engine

from crawler import ENVIRONMENTS, crawl_environment, crawl_indicator

DATABASE_URL = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)


@cli
def crawl(env: str, dataset: str = "") -> None:
    """Crawl one or all environments. Use 'demo', 'prod', or 'all'.
    Pass --dataset <id_or_slug> to recrawl a single indicator."""
    if env not in ENVIRONMENTS and env != "all":
        raise ValueError(f"Unknown environment: {env!r}. Use one of: {', '.join(ENVIRONMENTS)} or 'all'")

    if dataset:
        if env == "all":
            raise ValueError("--dataset cannot be combined with env 'all'")
        with Session(engine) as session:
            crawl_indicator(env, dataset, session)
    else:
        envs = list(ENVIRONMENTS.keys()) if env == "all" else [env]
        for e in envs:
            with Session(engine) as session:
                crawl_environment(e, session)


if __name__ == "__main__":
    run()
