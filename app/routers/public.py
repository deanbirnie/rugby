from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Match
from app.pot import closest_predictions, get_current_pot, get_leaderboard, get_payout_for_match
from app.templating import templates
from app.timeutil import now_local

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    pot = get_current_pot(db)
    now = now_local()
    next_match = (
        db.execute(
            select(Match)
            .where(Match.kickoff_at >= now, Match.bok_score.is_(None))
            .order_by(Match.kickoff_at.asc())
        )
        .scalars()
        .first()
    )
    recent_matches = (
        db.execute(
            select(Match)
            .where(Match.bok_score.is_not(None))
            .order_by(Match.kickoff_at.desc())
            .limit(3)
        )
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        request,
        "home.html",
        {"pot": pot, "next_match": next_match, "recent_matches": recent_matches},
    )


@router.get("/matches", response_class=HTMLResponse)
def matches_list(request: Request, tab: str = "upcoming", db: Session = Depends(get_db)):
    if tab == "past":
        matches = (
            db.execute(
                select(Match).where(Match.bok_score.is_not(None)).order_by(Match.kickoff_at.desc())
            )
            .scalars()
            .all()
        )
    else:
        tab = "upcoming"
        matches = (
            db.execute(
                select(Match)
                .where(Match.bok_score.is_(None))
                .order_by(Match.kickoff_at.asc())
            )
            .scalars()
            .all()
        )
    return templates.TemplateResponse(
        request, "matches_list.html", {"matches": matches, "tab": tab}
    )


def _match_predictions(match: Match) -> list:
    """Public prediction list: closest-first once resolved, otherwise in
    submission order so the table reads like a live feed.
    """
    if match.is_resolved:
        return closest_predictions(match)
    return sorted(match.predictions, key=lambda p: p.submitted_at)


@router.get("/matches/{match_id}", response_class=HTMLResponse)
def match_detail(match_id: int, request: Request, db: Session = Depends(get_db)):
    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)

    payout = get_payout_for_match(db, match.id) if match.is_resolved else None

    return templates.TemplateResponse(
        request,
        "match_detail.html",
        {
            "match": match,
            "predictions": _match_predictions(match),
            "payout": payout,
            "entry_count": len(match.predictions),
        },
    )


@router.get("/matches/{match_id}/predictions-table", response_class=HTMLResponse)
def match_predictions_table(match_id: int, request: Request, db: Session = Depends(get_db)):
    """htmx polling target so the predictions list updates live while
    predictions are still coming in.
    """
    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)

    return templates.TemplateResponse(
        request,
        "_predictions_table.html",
        {"match": match, "predictions": _match_predictions(match)},
    )


@router.get("/leaderboard", response_class=HTMLResponse)
def leaderboard(request: Request, db: Session = Depends(get_db)):
    rows = get_leaderboard(db)
    return templates.TemplateResponse(request, "leaderboard.html", {"rows": rows})
