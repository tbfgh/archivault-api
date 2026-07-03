#!/usr/bin/env python3
"""
Generates the first indexer token and prints it to stdout.
Called by setup.sh — prints only the token string for capture.
"""
import sys
import os
import secrets
import string
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import SessionLocal
from app.models import IndexerToken


def generate_token():
    db = SessionLocal()
    try:
        alphabet = string.ascii_letters + string.digits
        token_str = "av_" + "".join(secrets.choice(alphabet) for _ in range(48))
        token = IndexerToken(name="Default Indexer", token=token_str, is_active=True)
        db.add(token)
        db.commit()
        # Print only the token — setup.sh captures this
        print(token_str)
    finally:
        db.close()


if __name__ == "__main__":
    generate_token()
