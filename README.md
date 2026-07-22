# Bokke Predictions 🏉

A lightweight score-prediction pool for your Springbok match-viewing crew.
One shared pot carries over from match to match; whoever nails the exact
score wins the whole thing and the pot resets. Built to be simple, low on
personal data, and easy to self-host.

- **Stack:** FastAPI + HTMX + Jinja2 templates + SQLite, no build step, no JS framework. Dependencies are managed with [uv](https://docs.astral.sh/uv/).
- **No real accounts.** Predictors identify themselves with just a name and
  cellphone number (used only to recognise repeat predictors for the season
  leaderboard — never shown anywhere in the UI). Admin access is a single
  shared password.
- **QR-code driven.** Each match gets a unique QR code you print out; people
  scan it, type their prediction, and optionally mark themselves as paid.

## How it works

- **The pot** carries forward across matches. The admin sets a buy-in amount
  per match, and every prediction adds that buy-in to the pot — no separate
  "have you paid" step for predictors. Whether the cash has actually been
  handed over is tracked separately by the admin (see below) and never
  affects the pot total.
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

   Generate the three secrets it asks for (run this once per secret):

   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"   # SESSION_SECRET, PHONE_HASH_SECRET, PHONE_ENCRYPTION_KEY
   ```

   Any long random string works for all three. The app refuses to start
   while `PHONE_ENCRYPTION_KEY` is missing or still `change-me`, so a
   misconfigured deployment fails at boot rather than when your first
   friend tries to submit a prediction.

   Set `ADMIN_PASSWORD` to whatever you like — it doesn't need to be
   fancy, this app isn't protecting anything sensitive. `APP_TIMEZONE`
   and `DEFAULT_COUNTRY_CODE` are optional and default to South Africa;
   change `APP_TIMEZONE` (any IANA name) if your crew watches from
   elsewhere, since it controls when predictions lock at kickoff.

   Set `BASE_URL` to your public hostname (e.g. your Cloudflare Tunnel
   domain) — it's baked into the QR codes and printed posters. Without it
   they fall back to the address the container sees on the request, which
   is usually an internal IP your friends' phones can't reach.

2. Build and run:

   ```bash
   docker compose up -d --build
   ```

   The app listens on port 8000 (mapped to 8000 on the host). The SQLite
   database lives in a named Docker volume (`bokke-data`) so it survives
   container rebuilds.

3. Point your Cloudflare Tunnel at `http://localhost:8000` (or the container
   name `bokke-predictions` if the tunnel runs in the same Docker network).

### Using the published image instead of building locally

Every push to `main` builds and publishes an image to GitHub Container
Registry via `.github/workflows/docker-publish.yml` — no need to `git clone`
or build on the server itself. The image is at
`ghcr.io/deanbirnie/rugby:latest` (also tagged with the short commit SHA,
e.g. `ghcr.io/deanbirnie/rugby:sha-1a2b3c4`, if you want to pin a specific
build).

**One-time setup:** the package is private by default the first time the
workflow runs. Go to the package's page on GitHub (Profile → Packages →
`rugby`) → **Package settings** → change visibility to **Public**, so your
server can `docker pull` without authenticating.

Then, on the server, use a compose file that pulls instead of builds:

```yaml
services:
  bokke-predictions:
    image: ghcr.io/deanbirnie/rugby:latest
    container_name: bokke-predictions
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - bokke-data:/app/data

volumes:
  bokke-data:
```

```bash
docker compose pull && docker compose up -d
```

Re-running those two commands after a merge to `main` (once the workflow
has finished) picks up the new image.

### Without Docker (local dev with uv)

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you
don't have it, then:

```bash
uv sync                      # create .venv and install the locked deps
cp .env.example .env         # fill in secrets (see above)
uv run --env-file .env uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`uv run` uses the project virtualenv, so you don't need to activate anything;
`--env-file .env` loads your secrets into the process (in production these
come from docker-compose's `env_file` instead). To add or change a dependency,
run `uv add <package>` (or edit `pyproject.toml`) and commit the updated
`uv.lock`.

## Using it

1. Go to `/admin`, log in with `ADMIN_PASSWORD`.
2. **Add Match** — opponent, competition, venue, kickoff date/time, and the
   buy-in amount for that match.
3. You're redirected to a QR page (`/admin/matches/{id}/qr`) with a
   **Download A4 Poster (PDF)** button — a print-ready, Springbok-themed
   poster with the match details and QR code. Print it and stick it up
   wherever you're watching the game.
4. People scan the QR and enter their cellphone number (0- and +27-style
   numbers are treated as the same). If the number is recognised they're
   greeted by name and go straight to their prediction — first-timers are
   asked for their name once. Then they enter their score. Every prediction
   is in the pot automatically; predictors never see anything about payment.
5. Whenever cash changes hands, open **Predictions** on the match and tick
   people off as paid. This is purely your own record of who still owes —
   it never changes the pot and is never shown to predictors. The page
   shows a running "X / Y paid · Collected / Outstanding" summary.
6. After the match, enter the final score. Anyone with an exact match is
   automatically flagged as a winner, the payout split is shown (admin-only),
   and the pot resets for the next match.
7. The public site (`/`, `/matches`, `/leaderboard`) shows the running pot,
   upcoming fixtures, everyone's predictions for each match (updating live
   while predictions are open), past results with who was closest, and
   season-long standings — with no money figures beyond the current pot
   total (who's paid and payout splits stay admin-only).

## Maintenance scripts

Everything in `scripts/` is an admin tool that runs **inside the container**
(`docker exec`), not through the website. That's deliberate: phone numbers
are stored encrypted and are never decrypted by the running web app — the
web admin sits behind one shared password, while these scripts require
access to the server itself, a much stronger gate. The container already
has the app's secrets and database, so no extra setup is needed.

| Script | What it does |
|---|---|
| `scripts/list_players.py` | List every player: id, name, decrypted number, prediction/paid/win counts, first-seen date |
| `scripts/decrypt_phone.py` | Look up one person's number by (partial) name |
| `scripts/merge_players.py` | Fold a duplicate account into the real one (dry-run by default) |

### List all players

The starting point for any player admin — shows the ids the other scripts
need:

```bash
docker exec -it bokke-predictions python scripts/list_players.py
```

### Look up one person's number

E.g. to chase a buy-in:

```bash
docker exec -it bokke-predictions python scripts/decrypt_phone.py "Dean Birnie"
```

Matches partial names, case-insensitively.

### Merge a duplicate account

If someone typos their number at the phone step they won't be recognised
and will end up with a second account splitting their season history (the
tell: a regular gets the "First time? Welcome!" screen). Find both ids
with `list_players.py`, then merge the typo'd account into the real one.
Accounts are picked purely by id, so identical display names are fine.

The **first** id survives, keeping its name and (correct) number; all
predictions move across; the duplicate account and its number are
deleted. If both accounts predicted the same match, the most recently
updated prediction wins, and it counts as paid if either was.

```bash
# preview first (writes nothing, shows exactly what would happen):
docker exec -it bokke-predictions python scripts/merge_players.py 3 7
# then apply:
docker exec -it bokke-predictions python scripts/merge_players.py 3 7 --yes
```

### Running them without Docker

For a local (uv) setup, run any script with the same `.env` the app uses:

```bash
uv run --env-file .env python scripts/list_players.py
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
