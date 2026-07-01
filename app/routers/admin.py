from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppSettings, Match, Player, Prediction
from app.pot import compute_pot_timeline, get_payout_for_match, get_or_create_settings
from app.qr import generate_qr_png
from app.security import require_admin, verify_admin_password
from app.templating import templates

router = APIRouter(prefix="/admin")


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.get("", response_class=HTMLResponse)
def admin_root(request: Request):
    if request.session.get("is_admin"):
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return RedirectResponse(url="/admin/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if request.session.get("is_admin"):
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return templates.TemplateResponse(request, "admin/login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, password: str = Form(...)):
    if verify_admin_password(password):
        request.session["is_admin"] = True
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return templates.TemplateResponse(
        request, "admin/login.html", {"error": "Incorrect password."}, status_code=401
    )


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def dashboard(request: Request, db: Session = Depends(get_db)):
    settings = get_or_create_settings(db)
    # Compute the pot timeline once; it yields both the current pot and the
    # per-match payout map, avoiding an O(N^2) recompute per past match.
    payouts, pot = compute_pot_timeline(db)
    upcoming = (
        db.query(Match)
        .filter(Match.bok_score.is_(None))
        .order_by(Match.kickoff_at.asc())
        .all()
    )
    past = (
        db.query(Match)
        .filter(Match.bok_score.is_not(None))
        .order_by(Match.kickoff_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "pot": pot,
            "settings": settings,
            "upcoming": upcoming,
            "past": past,
            "payouts": payouts,
        },
    )


@router.get("/matches/new", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def new_match_form(request: Request):
    return templates.TemplateResponse(
        request, "admin/match_form.html", {"match": None, "error": None}
    )


@router.post("/matches/new", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def new_match_submit(
    request: Request,
    opponent: str = Form(...),
    competition: str = Form(""),
    venue: str = Form(""),
    kickoff_at: str = Form(...),
    buy_in_amount: float = Form(0),
    db: Session = Depends(get_db),
):
    try:
        kickoff_dt = datetime.fromisoformat(kickoff_at)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "admin/match_form.html",
            {"match": None, "error": "Invalid kickoff date/time."},
            status_code=400,
        )

    match = Match(
        opponent=opponent.strip(),
        competition=competition.strip() or None,
        venue=venue.strip() or None,
        kickoff_at=kickoff_dt,
        buy_in_amount=max(0.0, buy_in_amount),
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return RedirectResponse(url=f"/admin/matches/{match.id}/qr", status_code=303)


@router.get(
    "/matches/{match_id}/edit", response_class=HTMLResponse, dependencies=[Depends(require_admin)]
)
def edit_match_form(match_id: int, request: Request, db: Session = Depends(get_db)):
    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)
    return templates.TemplateResponse(
        request, "admin/match_form.html", {"match": match, "error": None}
    )


@router.post(
    "/matches/{match_id}/edit", response_class=HTMLResponse, dependencies=[Depends(require_admin)]
)
def edit_match_submit(
    match_id: int,
    request: Request,
    opponent: str = Form(...),
    competition: str = Form(""),
    venue: str = Form(""),
    kickoff_at: str = Form(...),
    buy_in_amount: float = Form(0),
    db: Session = Depends(get_db),
):
    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)

    try:
        kickoff_dt = datetime.fromisoformat(kickoff_at)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "admin/match_form.html",
            {"match": match, "error": "Invalid kickoff date/time."},
            status_code=400,
        )

    match.opponent = opponent.strip()
    match.competition = competition.strip() or None
    match.venue = venue.strip() or None
    match.kickoff_at = kickoff_dt
    if not match.is_resolved:
        match.buy_in_amount = max(0.0, buy_in_amount)
    db.commit()
    return RedirectResponse(url="/admin/dashboard?msg=Match updated", status_code=303)


@router.post(
    "/matches/{match_id}/result", response_class=HTMLResponse, dependencies=[Depends(require_admin)]
)
def enter_result(
    match_id: int,
    request: Request,
    bok_score: int = Form(...),
    opponent_score: int = Form(...),
    db: Session = Depends(get_db),
):
    from app.pot import apply_result

    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)
    if bok_score < 0 or opponent_score < 0:
        return RedirectResponse(
            url=f"/admin/matches/{match_id}/edit?msg=Scores can't be negative&type=error",
            status_code=303,
        )

    apply_result(db, match, bok_score, opponent_score)
    return RedirectResponse(
        url=f"/admin/matches/{match_id}/predictions?msg=Result saved", status_code=303
    )


@router.get(
    "/matches/{match_id}/predictions",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
def match_predictions(match_id: int, request: Request, db: Session = Depends(get_db)):
    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)

    predictions = sorted(
        match.predictions,
        key=lambda p: (p.diff if match.is_resolved else 0, p.submitted_at),
    )
    payout = get_payout_for_match(db, match.id) if match.is_resolved else None

    return templates.TemplateResponse(
        request,
        "admin/predictions.html",
        {"match": match, "predictions": predictions, "payout": payout},
    )


@router.post(
    "/predictions/{prediction_id}/toggle-paid",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
def toggle_paid(prediction_id: int, request: Request, db: Session = Depends(get_db)):
    prediction = db.get(Prediction, prediction_id)
    if prediction is None:
        return HTMLResponse("Not found", status_code=404)
    prediction.paid = not prediction.paid
    db.commit()
    return templates.TemplateResponse(
        request, "admin/_paid_toggle.html", {"prediction": prediction}
    )


@router.get(
    "/matches/{match_id}/qr", response_class=HTMLResponse, dependencies=[Depends(require_admin)]
)
def qr_print(match_id: int, request: Request, db: Session = Depends(get_db)):
    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)
    predict_url = f"{_base_url(request)}/predict/{match.qr_token}"
    return templates.TemplateResponse(
        request, "admin/qr_print.html", {"match": match, "predict_url": predict_url}
    )


@router.get("/qr/{qr_token}.png")
def qr_image(qr_token: str, request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import Response

    match = db.query(Match).filter(Match.qr_token == qr_token).first()
    if match is None:
        return HTMLResponse("Not found", status_code=404)
    predict_url = f"{_base_url(request)}/predict/{match.qr_token}"
    png = generate_qr_png(predict_url)
    return Response(content=png, media_type="image/png")


@router.get("/matches/{match_id}/poster.pdf", dependencies=[Depends(require_admin)])
def match_poster(match_id: int, request: Request, db: Session = Depends(get_db)):
    import re

    from fastapi.responses import Response

    from app.pdf import build_match_poster

    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)

    predict_url = f"{_base_url(request)}/predict/{match.qr_token}"
    pdf = build_match_poster(match, predict_url)

    slug = re.sub(r"[^a-z0-9]+", "-", match.opponent.lower()).strip("-") or "match"
    filename = f"bokke-vs-{slug}-{match.kickoff_at:%Y-%m-%d}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/players", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def players_list(request: Request, db: Session = Depends(get_db)):
    players = db.query(Player).order_by(Player.display_name.asc()).all()
    return templates.TemplateResponse(request, "admin/players.html", {"players": players})


@router.post(
    "/players/{player_id}/rename", response_class=HTMLResponse, dependencies=[Depends(require_admin)]
)
def rename_player(
    player_id: int, request: Request, display_name: str = Form(...), db: Session = Depends(get_db)
):
    player = db.get(Player, player_id)
    if player is None:
        return HTMLResponse("Not found", status_code=404)
    player.display_name = display_name.strip()
    db.commit()
    return RedirectResponse(url="/admin/players", status_code=303)


@router.get("/settings", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def settings_form(request: Request, db: Session = Depends(get_db)):
    settings = get_or_create_settings(db)
    return templates.TemplateResponse(request, "admin/settings.html", {"settings": settings})


@router.post("/settings", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def settings_submit(
    request: Request, starting_pot_balance: float = Form(0), db: Session = Depends(get_db)
):
    settings = db.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1)
        db.add(settings)
    settings.starting_pot_balance = max(0.0, starting_pot_balance)
    db.commit()
    return RedirectResponse(url="/admin/dashboard?msg=Settings saved", status_code=303)
