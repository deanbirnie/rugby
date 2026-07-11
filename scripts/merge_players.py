#!/usr/bin/env python3
"""Merge a duplicate player account into the real one.

Typical cause: someone typos their number at the phone step, isn't
recognised, and ends up with a second account carrying part of their
season history. Find both ids with scripts/list_players.py, then:

    docker exec -it bokke-predictions python scripts/merge_players.py KEEP_ID DUPLICATE_ID
    docker exec -it bokke-predictions python scripts/merge_players.py KEEP_ID DUPLICATE_ID --yes

KEEP_ID is the account that survives (the one with the CORRECT number —
its name, number and identity are untouched). All predictions move from
DUPLICATE_ID onto it, then the duplicate account is deleted. If both
accounts predicted the same match, the most recently updated prediction
wins, and it counts as paid if either of the two was paid (the cash was
handed over either way).

Without --yes nothing is written — you get a preview of exactly what
would happen.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import Player
from app.security import decrypt_phone


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--yes"]
    apply = "--yes" in sys.argv[1:]
    if len(args) != 2 or not all(a.isdigit() for a in args):
        print(__doc__)
        sys.exit(1)
    keep_id, dupe_id = int(args[0]), int(args[1])
    if keep_id == dupe_id:
        print("KEEP_ID and DUPLICATE_ID are the same account.")
        sys.exit(1)

    db = SessionLocal()
    try:
        keep = db.get(Player, keep_id)
        dupe = db.get(Player, dupe_id)
        for pid, player in ((keep_id, keep), (dupe_id, dupe)):
            if player is None:
                print(f"No player with id {pid}. Run scripts/list_players.py to see ids.")
                sys.exit(1)

        print(f"KEEP   #{keep.id}  {keep.display_name}  {decrypt_phone(keep.phone_encrypted)}")
        print(f"MERGE  #{dupe.id}  {dupe.display_name}  {decrypt_phone(dupe.phone_encrypted)}")
        print()

        keep_by_match = {p.match_id: p for p in keep.predictions}
        for pred in list(dupe.predictions):
            label = f"Springboks vs {pred.match.opponent} ({pred.match.kickoff_at:%Y-%m-%d})"
            clash = keep_by_match.get(pred.match_id)
            if clash is None:
                print(f"  move   {label}: {pred.predicted_bok_score}-{pred.predicted_opponent_score}")
                pred.player = keep
            elif pred.updated_at > clash.updated_at:
                print(
                    f"  clash  {label}: keeping duplicate's newer "
                    f"{pred.predicted_bok_score}-{pred.predicted_opponent_score}, dropping "
                    f"{clash.predicted_bok_score}-{clash.predicted_opponent_score}"
                )
                pred.paid = pred.paid or clash.paid
                # Delete the old row before reassigning, or the UPDATE flushes
                # first and trips the (match_id, player_id) unique constraint.
                db.delete(clash)
                db.flush()
                pred.player = keep
            else:
                print(
                    f"  clash  {label}: keeping #{keep.id}'s newer "
                    f"{clash.predicted_bok_score}-{clash.predicted_opponent_score}, dropping "
                    f"{pred.predicted_bok_score}-{pred.predicted_opponent_score}"
                )
                clash.paid = clash.paid or pred.paid
                db.delete(pred)

        print(f"  delete player #{dupe.id} ({dupe.display_name})")
        db.flush()
        db.delete(dupe)

        if apply:
            db.commit()
            print("\nMerged.")
        else:
            db.rollback()
            print("\nDry run - nothing changed. Re-run with --yes to apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
