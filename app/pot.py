"""Pot value and season-standings business logic.

The pot carries forward match to match and only resets to zero once someone
lands an exact score and the cash is handed over. Rather than store a running
ledger value that can drift, the current pot (and each historical payout) is
always recomputed from the match/prediction rows, walked in chronological
order.
"""
from sqlalchemy.orm import Session

from app.models import AppSettings, Match, Player


def get_or_create_settings(db: Session) -> AppSettings:
    settings = db.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1, starting_pot_balance=0)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def compute_pot_timeline(db: Session):
    """Returns (payouts_by_match_id, current_pot).

    payouts_by_match_id maps a resolved match's id to
    {"payout_total": float, "winners": [Prediction, ...], "per_winner": float}
    for matches where someone won the pot. Matches with no winner map to None.
    """
    settings = get_or_create_settings(db)
    matches = db.query(Match).order_by(Match.kickoff_at.asc()).all()

    running = float(settings.starting_pot_balance)
    payouts: dict[int, dict | None] = {}

    for match in matches:
        running += match.paid_contribution
        winners = [p for p in match.predictions if p.is_winner]
        if winners:
            payouts[match.id] = {
                "payout_total": running,
                "winners": winners,
                "per_winner": running / len(winners),
            }
            running = 0.0
        else:
            payouts[match.id] = None

    return payouts, running


def get_current_pot(db: Session) -> float:
    _, current_pot = compute_pot_timeline(db)
    return current_pot


def get_payout_for_match(db: Session, match_id: int) -> dict | None:
    payouts, _ = compute_pot_timeline(db)
    return payouts.get(match_id)


def apply_result(db: Session, match: Match, bok_score: int, opponent_score: int) -> None:
    from app.timeutil import now_local

    match.bok_score = bok_score
    match.opponent_score = opponent_score
    match.result_entered_at = now_local()

    for prediction in match.predictions:
        prediction.is_winner = (
            prediction.predicted_bok_score == bok_score
            and prediction.predicted_opponent_score == opponent_score
        )

    db.commit()


def get_leaderboard(db: Session) -> list[dict]:
    players = db.query(Player).all()
    rows = []
    for player in players:
        resolved = [p for p in player.predictions if p.match.is_resolved]
        if not resolved:
            continue
        diffs = [p.diff for p in resolved]
        wins = sum(1 for p in resolved if p.is_winner)
        rows.append(
            {
                "player": player,
                "predictions_count": len(resolved),
                "wins": wins,
                "avg_diff": sum(diffs) / len(diffs),
            }
        )
    rows.sort(key=lambda r: (-r["wins"], r["avg_diff"]))
    return rows


def closest_predictions(match: Match) -> list:
    """Predictions for a resolved match, closest first."""
    if not match.is_resolved:
        return []
    return sorted(match.predictions, key=lambda p: p.diff)
