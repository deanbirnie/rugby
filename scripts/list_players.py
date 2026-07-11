#!/usr/bin/env python3
"""List every player with their decrypted phone number and season stats.

Deliberately NOT exposed in the web app — phone numbers never surface in the
UI. Run it inside the container, where the app's secrets are available:

    docker exec -it bokke-predictions python scripts/list_players.py

Spotting a duplicate (same person under two numbers, usually a typo at the
phone step) is what scripts/merge_players.py is for.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import Player
from app.security import decrypt_phone


def main() -> None:
    db = SessionLocal()
    try:
        players = db.query(Player).order_by(Player.display_name.asc()).all()
        if not players:
            print("No players yet.")
            return

        header = f"{'id':>4}  {'name':<24} {'phone':<14} {'preds':>5} {'paid':>4} {'wins':>4}  first seen"
        print(header)
        print("-" * len(header))
        for p in players:
            resolved = [x for x in p.predictions if x.match.is_resolved]
            wins = sum(1 for x in resolved if x.is_winner)
            paid = sum(1 for x in p.predictions if x.paid)
            print(
                f"{p.id:>4}  {p.display_name[:24]:<24} {decrypt_phone(p.phone_encrypted):<14}"
                f" {len(p.predictions):>5} {paid:>4} {wins:>4}  {p.created_at:%Y-%m-%d}"
            )
        print(f"\n{len(players)} player(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
