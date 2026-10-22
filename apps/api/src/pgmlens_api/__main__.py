"""``python -m pgmlens_api``: serve the API (and the built dashboard, if given) on one port."""

from __future__ import annotations

import argparse
import os


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pgmlens-api", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--web", help="Folder with the built dashboard (apps/web/dist).")
    args = parser.parse_args(argv)
    if args.web:
        os.environ["PGMLENS_WEB_DIR"] = args.web

    import uvicorn

    uvicorn.run("pgmlens_api.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
