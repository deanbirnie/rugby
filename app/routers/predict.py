from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Match, Player, Prediction
from app.pot import get_current_pot
from app.security import encrypt_phone, hash_phone, normalize_phone
from app.templating import templates

router = APIRouter()

COOKIE_NAME = "bokke_name"
COOKIE_PHONE = "bokke_phone"


def _get_match_or_404(db: Session, qr_token: str) -> Match | None:
    return db.query(Match).filter(Match.qr_token == qr_token).first()


@router.get("/predict/{qr_token}", response_class=HTMLResponse)
def predict_form(qr_token: str, request: Request, db: Session = Depends(get_db)):
    match = _get_match_or_404(db, qr_token)
    if match is None:
        return HTMLResponse("Match not found. Check the QR code / link.", status_code=404)

    saved_name = request.cookies.get(COOKIE_NAME, "")
    saved_phone = request.cookies.get(COOKIE_PHONE, "")

    return templates.TemplateResponse(
        request,
        "predict_form.html",
        {
            "match": match,
            "entry_count": len(match.predictions),
            "saved_name": saved_name,
            "saved_phone": saved_phone,
            "error": None,
        },
    )


@router.post("/predict/{qr_token}", response_class=HTMLResponse)
def predict_submit(
    qr_token: str,
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    bok_score: int = Form(...),
    opponent_score: int = Form(...),
    paid_now: bool = Form(False),
    db: Session = Depends(get_db),
):
    match = _get_match_or_404(db, qr_token)
    if match is None:
        return HTMLResponse("Match not found. Check the QR code / link.", status_code=404)

    name = name.strip()
    normalized = normalize_phone(phone)

    error = None
    if match.is_locked:
        error = "Predictions are closed for this match."
    elif not name:
        error = "Please enter your name."
    elif len(normalized) < 9:
        error = "Please enter a valid cellphone number."
    elif bok_score < 0 or opponent_score < 0:
        error = "Scores can't be negative."

    if error:
        return templates.TemplateResponse(
            request,
            "predict_form.html",
            {
                "match": match,
                "entry_count": len(match.predictions),
                "saved_name": name,
                "saved_phone": phone,
                "error": error,
            },
            status_code=400,
        )

    phone_hash = hash_phone(normalized)
    player = db.query(Player).filter(Player.phone_hash == phone_hash).first()
    if player is None:
        player = Player(
            display_name=name,
            phone_hash=phone_hash,
            phone_encrypted=encrypt_phone(normalized),
        )
        db.add(player)
        db.flush()
    else:
        player.display_name = name

    prediction = (
        db.query(Prediction)
        .filter(Prediction.match_id == match.id, Prediction.player_id == player.id)
        .first()
    )
    if prediction is None:
        prediction = Prediction(match_id=match.id, player_id=player.id)
        db.add(prediction)

    prediction.predicted_bok_score = bok_score
    prediction.predicted_opponent_score = opponent_score
    if paid_now:
        prediction.paid = True

    db.commit()

    response = RedirectResponse(url=f"/predict/{qr_token}/success", status_code=303)
    response.set_cookie(COOKIE_NAME, name, max_age=60 * 60 * 24 * 365)
    response.set_cookie(COOKIE_PHONE, phone, max_age=60 * 60 * 24 * 365)
    return response


@router.get("/predict/{qr_token}/success", response_class=HTMLResponse)
def predict_success(qr_token: str, request: Request, db: Session = Depends(get_db)):
    match = _get_match_or_404(db, qr_token)
    if match is None:
        return HTMLResponse("Match not found.", status_code=404)

    saved_name = request.cookies.get(COOKIE_NAME, "")
    saved_phone = request.cookies.get(COOKIE_PHONE, "")
    prediction = None
    if saved_phone:
        phone_hash = hash_phone(normalize_phone(saved_phone))
        player = db.query(Player).filter(Player.phone_hash == phone_hash).first()
        if player:
            prediction = (
                db.query(Prediction)
                .filter(Prediction.match_id == match.id, Prediction.player_id == player.id)
                .first()
            )

    return templates.TemplateResponse(
        request,
        "predict_success.html",
        {"match": match, "prediction": prediction, "pot": get_current_pot(db)},
    )
