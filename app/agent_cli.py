"""Run the autonomous paper agent once: ``python -m app.agent_cli``."""

import argparse
import json

from app.trading_agent import run_sync


def main() -> None:
    parser = argparse.ArgumentParser(description="Run drrrd's Alpaca paper-options agent")
    parser.add_argument("--dry-run", action="store_true", help="research and gate without ordering")
    args = parser.parse_args()
    print(json.dumps(run_sync(execute=not args.dry_run), indent=2))


if __name__ == "__main__":
    main()
