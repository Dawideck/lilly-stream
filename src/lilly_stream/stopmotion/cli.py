from __future__ import annotations

import argparse
import logging
from pathlib import Path

from lilly_stream.capture.camera import Camera
from lilly_stream.config import load_config
from lilly_stream.stopmotion.server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the lilly-stream stop-motion Pi server.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--tmp-dir", type=Path, default=Path("stopmotion_tmp"))
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    config = load_config(args.config)
    camera = Camera()
    app = create_app(camera, tmp_dir=args.tmp_dir, storage_dir=config.capture.storage_dir)
    app.run(host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
