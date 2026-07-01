#!/usr/bin/env python3
"""Recover a player's actual phone number from the database, for the rare
case you need to contact someone (e.g. about an unpaid buy-in).

This is deliberately NOT exposed anywhere in the web app. Run it directly
against the container/database with the same PHONE_ENCRYPTION_KEY the app
uses:

    docker exec -it bokke-predictions python scripts/decrypt_phone.py "Dean Birnie"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import Player
from app.security import decrypt_phone


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <player display name>")
        sys.exit(1)

    name = sys.argv[1]
    db = SessionLocal()
    try:
        matches = db.query(Player).filter(Player.display_name.ilike(f"%{name}%")).all()
        if not matches:
            print(f"No player found matching '{name}'.")
            sys.exit(1)
        for player in matches:
            phone = decrypt_phone(player.phone_encrypted)
            print(f"{player.display_name} (id={player.id}): {phone}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
