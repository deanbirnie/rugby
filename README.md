# Bokke Predictions 🏉

A lightweight score-prediction pool for your Springbok match-viewing crew.
One shared pot carries over from match to match; whoever nails the exact
score wins the whole thing and the pot resets. Built to be simple, low on
personal data, and easy to self-host.

- **Stack:** FastAPI + HTMX + Jinja2 templates + SQLite, no build step, no JS framework.
- **No real accounts.** Predictors identify themselves with just a name and
  cellphone number (used only to recognise repeat predictors for the season
  leaderboard — never shown anywhere in the UI). Admin access is a single
  shared password.
- **QR-code driven.** Each match gets a unique QR code you print out; people
  scan it, type their prediction, and optionally mark themselves as paid.

## How it works

- **The pot** carries forward across matches. The admin sets a buy-in amount
  per match; every predictor who pays that buy-in (ticked at prediction time,
  or marked paid later by the admin) adds to the pot.
- **Winning** requires an *exact* score match (both team scores correct). If
  more than one person nails it, the pot splits evenly between them and all
  are recorded as winners. The pot then resets to zero for the next match.
- **Money is never shown publicly.** The current pot total is public (it's
  the whole point of the site), but *who won how much* is admin-only. The
  public site only ever shows "🏆 winner" against a person's name, never a
  rand amount.
- **Identity without logins:** the first time someone predicts, they type
  their name + cellphone number. The number is normalized and hashed so the
  same person is recognised next time even if they type a different
  nickname — their display name just gets updated to whatever they typed
  most recently. The number itself is stored encrypted and is never
  decrypted anywhere in the web app; see [Recovering a phone number](#recovering-a-phone-number)
  if you ever genuinely need it.

## Running with Docker

1. Copy the env file and fill in real secrets:

   ```bash
   cp .env.example .env
   ```

   Generate the three secrets it asks for:

   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"   # SESSION_SECRET
   python3 -c "import secrets; print(secrets.token_hex(32))"   # PHONE_HASH_SECRET
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # PHONE_ENCRYPTION_KEY
   ```

   Set `ADMIN_PASSWORD` to whatever you like — it doesn't need to be
   fancy, this app isn't protecting anything sensitive. `APP_TIMEZONE`
   and `DEFAULT_COUNTRY_CODE` are optional and default to South Africa;
   change `APP_TIMEZONE` (any IANA name) if your crew watches from
   elsewhere, since it controls when predictions lock at kickoff.

2. Build and run:

   ```bash
   docker compose up -d --build
   ```

   The app listens on port 8000 (mapped to 8000 on the host). The SQLite
   database lives in a named Docker volume (`bokke-data`) so it survives
   container rebuilds.

3. Point your Cloudflare Tunnel at `http://localhost:8000` (or the container
   name `bokke-predictions` if the tunnel runs in the same Docker network).

### Without Docker

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ADMIN_PASSWORD=... SESSION_SECRET=... PHONE_HASH_SECRET=... PHONE_ENCRYPTION_KEY=...
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Using it

1. Go to `/admin`, log in with `ADMIN_PASSWORD`.
2. **Add Match** — opponent, competition, venue, kickoff date/time, and the
   buy-in amount for that match.
3. You're redirected to a printable QR page (`/admin/matches/{id}/qr`) —
   print it and stick it up wherever you're watching the game.
4. People scan the QR, type their name + cellphone number + score
   prediction, and optionally tick "I'm paying now".
5. Before or after the match, use **Predictions** on the match to tick off
   who's paid, if they didn't pay at prediction time.
6. After the match, enter the final score. Anyone with an exact match is
   automatically flagged as a winner, the payout split is shown (admin-only),
   and the pot resets for the next match.
7. The public site (`/`, `/matches`, `/leaderboard`) shows the running pot,
   upcoming fixtures, past results with who was closest, and season-long
   standings — with no dollar figures beyond the current pot total.

## Recovering a phone number

Phone numbers are stored encrypted and are never decrypted by the running
web app — there's no admin page for it, by design, to keep the attack
surface small. If you ever genuinely need to see one (e.g. to chase someone
for a buy-in), run this against the container with the same
`PHONE_ENCRYPTION_KEY` the app is using:

```bash
docker exec -it bokke-predictions python scripts/decrypt_phone.py "Dean Birnie"
```

## Data model notes

- `players` — one row per distinct cellphone number. `display_name` is just
  whatever they typed most recently.
- `matches` — one row per Springbok match, each with its own unique QR
  token, buy-in amount, and (once played) final score.
- `predictions` — one row per player per match; `paid` and `is_winner` are
  tracked here.
- The pot value is never stored as a single number — it's always
  recomputed from paid buy-ins since the last time someone won, so it can
  never drift out of sync with the underlying data.
