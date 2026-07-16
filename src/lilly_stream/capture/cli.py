from __future__ import annotations

import argparse
import logging
from pathlib import Path

from lilly_stream.capture.daemon import run
from lilly_stream.config import load_config, load_secrets


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the lilly-stream capture daemon.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--secrets", type=Path, default=Path("secrets.yaml"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    config = load_config(args.config)
    secrets = load_secrets(args.secrets)
    run(config, secrets)


if __name__ == "__main__":
    main()
