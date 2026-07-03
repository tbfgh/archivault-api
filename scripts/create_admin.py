#!/usr/bin/env python3
"""
Creates the first admin user from .env variables.
Run once during setup.sh — safe to re-run (skips if already exists).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.core.config import settings
from app.models import User, UserRole


def create_admin():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
        if existing:
            print(f"Admin user already exists: {settings.ADMIN_EMAIL}")
            return

        admin = User(
            email=settings.ADMIN_EMAIL,
            full_name=settings.ADMIN_FULL_NAME,
            hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
            role=UserRole.superadmin,
            is_active=True
        )
        db.add(admin)
        db.commit()
        print(f"Admin created: {settings.ADMIN_EMAIL}")
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
