"""Command line: `wiredbench serve`, `reset-password` and `check-upstream`."""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys

import uvicorn
from sqlalchemy import delete, select

from wiredbench.app import create_app
from wiredbench.config import HOTELS, Settings
from wiredbench.db import make_engine, make_session_factory, migrate
from wiredbench.models import AdminUser, AuthSession
from wiredbench.security import MIN_PASSWORD_LENGTH, hash_password
from wiredbench.services import furnidata
from wiredbench.services.upstream import Upstream, UpstreamError, furnidata_url


def serve() -> None:
    settings = Settings()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        create_app(settings), host=settings.host, port=settings.port, proxy_headers=False, server_header=False
    )


def reset_password() -> None:
    settings = Settings()
    password = getpass.getpass("New admin password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    engine = make_engine(settings.db_path)
    migrate(engine)
    with make_session_factory(engine).begin() as db:
        admin = db.scalar(select(AdminUser).limit(1))
        if admin is None:
            sys.exit("No admin exists yet. Start the server once first.")
        admin.password_hash = hash_password(password)
        db.execute(delete(AuthSession))
    print("Password changed. All sessions were signed out.")


def check_upstream(hotels: list[str]) -> None:
    """Used by the nightly workflow: can the furnidata still be fetched and parsed?"""
    upstream = Upstream()
    failed = False
    for hotel in hotels:
        if hotel not in HOTELS:
            sys.exit(f"Unknown hotel {hotel!r}. Choose from: {', '.join(HOTELS)}")
        try:
            fetched = upstream.get(furnidata_url(hotel), 64 * 2**20)
            if fetched.status != 200:
                raise UpstreamError(f"HTTP {fetched.status}")
            parsed = furnidata.parse(fetched.body)
            print(json.dumps({"hotel": hotel, "items": len(parsed.items), "wired": parsed.wired_count}))
        except (UpstreamError, furnidata.InvalidFurnidata) as exc:
            failed = True
            print(json.dumps({"hotel": hotel, "error": str(exc)}))
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="wiredbench")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="Start the server (default)")
    commands.add_parser("reset-password", help="Set a new admin password and sign everyone out")
    upstream = commands.add_parser("check-upstream", help="Check that Habbo gamedata can still be read")
    upstream.add_argument("hotels", nargs="*", default=["com", "sandbox"])
    args = parser.parse_args()
    if args.command == "reset-password":
        reset_password()
    elif args.command == "check-upstream":
        check_upstream(args.hotels)
    else:
        os.umask(0o077)
        serve()
