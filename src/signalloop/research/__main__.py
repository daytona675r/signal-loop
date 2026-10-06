"""Run one research operation synchronously, outside the HTTP server."""

import argparse
import json
import sys
from uuid import UUID

import httpx
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from signalloop.db.session import get_engine
from signalloop.domain.states import DomainError
from signalloop.research.contracts import ResearchCommand
from signalloop.research.hacker_news import HackerNewsComments
from signalloop.research.worker import ResearchFailed, ResearchWorker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, type=UUID, help="Exact HypothesisVersion UUID")
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    try:
        command = ResearchCommand(
            hypothesis_version_id=args.version, query=args.query, limit=args.limit
        )
        with httpx.Client() as client:
            result = ResearchWorker(
                sessionmaker(get_engine()), HackerNewsComments(client).collect
            ).run(command)
        print(result.model_dump_json(indent=2))
        return 0
    except (DomainError, ValidationError) as error:
        report = {"error": str(error)}
        if isinstance(error, ResearchFailed):
            report["agent_run_id"] = str(error.run_id)
        print(json.dumps(report), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
