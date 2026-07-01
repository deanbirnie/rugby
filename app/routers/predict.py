from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Match, Player, Prediction
from app.pot import get_current_pot
from app.security import (
    encrypt_phone,
    hash_phone,
    is_valid_sa_cell,
    normalize_phone,
)
from app.templating import templates

router = APIRouter()

COOKIE_PHONE = "bokke_phone"

PHONE_ERROR = "Please enter a valid South African cellphone number (e.g. 082 123 4567)."


def _get_match_or_404(db: Session, qr_token: str) -> Match | None:
    return db.query(Match).filter(Match.qr_token == qr_token).first()


def _find_player(db: Session, normalized: str) -> Player | None:
    return db.query(Player).filter(Player.phone_hash == hash_phone(normalized)).first()


def _find_prediction(db: Session, match: Match, player: Player) -> Prediction | None:
    return (
        db.query(Prediction)
        .filter(Prediction.match_id == match.id, Prediction.player_id == player.id)
        .first()
    )


def _render_phone_step(request, match, phone="", error=None, status_code=200):
    return templates.TemplateResponse(
        request,
        "predict_phone.html",
        {
            "match": match,
            "entry_count": len(match.predictions),
            "phone": phone,
            "error": error,
        },
        status_code=status_code,
    )


def _render_prediction_step(
    request, db, match, normalized, player, error=None, status_code=200
):
    existing = _find_prediction(db, match, player) if player else None
    return templates.TemplateResponse(
        request,
        "predict_form.html",
        {
            "match": match,
            "entry_count": len(match.predictions),
            "phone": normalized,
            "player": player,
            "existing": existing,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/predict/{qr_token}", response_class=HTMLResponse)
def predict_start(qr_token: str, request: Request, db: Session = Depends(get_db)):
    match = _get_match_or_404(db, qr_token)
    if match is None:
        return HTMLResponse("Match not found. Check the QR code / link.", status_code=404)

    saved_phone = request.cookies.get(COOKIE_PHONE, "")
    return _render_phone_step(request, match, phone=saved_phone)


@router.post("/predict/{qr_token}/identify", response_class=HTMLResponse)
def predict_identify(
    qr_token: str,
    request: Request,
    phone: str = Form(...),
    db: Session = Depends(get_db),
):
    match = _get_match_or_404(db, qr_token)
    if match is None:
        return HTMLResponse("Match not found. Check the QR code / link.", status_code=404)
    if match.is_locked:
        return _render_phone_step(request, match)

    normalized = normalize_phone(phone)
    if not is_valid_sa_cell(normalized):
        return _render_phone_step(
            request, match, phone=phone, error=PHONE_ERROR, status_code=400
        )

    player = _find_player(db, normalized)
    return _render_prediction_step(request, db, match, normalized, player)


@router.post("/predict/{qr_token}", response_class=HTMLResponse)
def predict_submit(
    qr_token: str,
    request: Request,
    phone: str = Form(...),
    bok_score: int = Form(...),
    opponent_score: int = Form(...),
    name: str = Form(""),
    paid_now: bool = Form(False),
    db: Session = Depends(get_db),
):
    match = _get_match_or_404(db, qr_token)
    if match is None:
        return HTMLResponse("Match not found. Check the QR code / link.", status_code=404)

    normalized = normalize_phone(phone)
    if not is_valid_sa_cell(normalized):
        # The phone came from the previous step's hidden field, so this only
        # happens if it was tampered with — start over at the phone step.
        return _render_phone_step(
            request, match, error=PHONE_ERROR, status_code=400
        )

    player = _find_player(db, normalized)
    name = name.strip()

    error = None
    if match.is_locked:
        error = "Predictions are closed for this match."
    elif player is None and not name:
        error = "Please enter your name."
    elif bok_score < 0 or opponent_score < 0:
        error = "Scores can't be negative."

    if error:
        return _render_prediction_step(
            request, db, match, normalized, player, error=error, status_code=400
        )

    if player is None:
        player = Player(
            display_name=name,
            phone_hash=hash_phone(normalized),
            phone_encrypted=encrypt_phone(normalized),
        )
        db.add(player)
        db.flush()

    prediction = _find_prediction(db, match, player)
    if prediction is None:
        prediction = Prediction(match_id=match.id, player_id=player.id)
        db.add(prediction)

    prediction.predicted_bok_score = bok_score
    prediction.predicted_opponent_score = opponent_score
    if paid_now:
        prediction.paid = True

    try:
        db.commit()
    except IntegrityError:
        # Two brand-new submissions for the same phone raced on the unique
        # phone_hash. Roll back and retry once against the row that won.
        db.rollback()
        player = _find_player(db, normalized)
        prediction = _find_prediction(db, match, player)
        if prediction is None:
            prediction = Prediction(match_id=match.id, player_id=player.id)
            db.add(prediction)
        prediction.predicted_bok_score = bok_score
        prediction.predicted_opponent_score = opponent_score
        if paid_now:
            prediction.paid = True
        db.commit()

    response = RedirectResponse(url=f"/predict/{qr_token}/success", status_code=303)
    response.set_cookie(COOKIE_PHONE, normalized, max_age=60 * 60 * 24 * 365)
    return response


@router.get("/predict/{qr_token}/success", response_class=HTMLResponse)
def predict_success(qr_token: str, request: Request, db: Session = Depends(get_db)):
    match = _get_match_or_404(db, qr_token)
    if match is None:
        return HTMLResponse("Match not found.", status_code=404)

    saved_phone = request.cookies.get(COOKIE_PHONE, "")
    prediction = None
    if saved_phone:
        player = _find_player(db, normalize_phone(saved_phone))
        if player:
            prediction = _find_prediction(db, match, player)

    return templates.TemplateResponse(
        request,
        "predict_success.html",
        {"match": match, "prediction": prediction, "pot": get_current_pot(db)},
    )
