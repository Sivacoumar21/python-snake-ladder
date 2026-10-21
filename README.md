# Python Snake & Ladder Quiz — deployable starter

A Flask web application for the BACSE101 *Problem Solving Using Python* syllabus. It includes account registration/login, invite-code rooms for up to four players, a Snake & Ladder board, 150 randomized Python questions, saved completion records, and an admin CSV export.

## Features
- Four-player room limit. The host creates a room and shares its six-character code.
- Random question per roll; a player does not see the same question twice until their personal 150-question bank is exhausted.
- Correct answers move the player; incorrect answers do not move them. Snakes and ladders apply after a correct answer.
- Exact roll required to land on square 100.
- Saved final scores and an admin-only results page/export.
- Question topics map to syllabus skills: Python fundamentals, control flow, strings/validation, collections, functions, recursion, algorithms, numerical problem solving, DNA/text processing, NumPy/Pandas, stacks/queues, geometric logic, flowcharts, sustainability/health applications, debugging, and data reporting.

## Run locally
Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

Set an admin account before first start:
```bash
# Windows PowerShell:
$env:ADMIN_USERNAME="teacher"
$env:ADMIN_PASSWORD="use-a-long-unique-password"
$env:SECRET_KEY="replace-with-a-long-random-secret"
python app.py
```

```bash
# macOS/Linux:
export ADMIN_USERNAME=teacher
export ADMIN_PASSWORD='use-a-long-unique-password'
export SECRET_KEY='replace-with-a-long-random-secret'
python app.py
```

Open http://127.0.0.1:5000. The database is SQLite by default (`snake_ladder.db` under Flask's instance database location). For a classroom test, create accounts for each player, create a room, and share the room code.

## Deploy to Render
1. Create a Git repository and upload this project.
2. In Render, choose **New → Blueprint** and select the repository; Render reads `render.yaml`.
3. Create a strong `ADMIN_USERNAME` and `ADMIN_PASSWORD` when prompted. Do not reuse personal passwords.
4. Wait for deployment, then visit the generated HTTPS URL. Register player accounts and test a four-player room.
5. Open `/admin` using the admin account to view saved scores and download CSV.

The blueprint creates a managed PostgreSQL database. If you deploy manually, configure:
- `DATABASE_URL` — PostgreSQL connection string
- `SECRET_KEY` — long random secret
- `ADMIN_USERNAME` and `ADMIN_PASSWORD` — initial admin credentials (admin is created on first startup only if that username does not already exist)

## Score calculation
Current implementation uses:

`score = 100 × (correct answers ÷ answered questions) × efficiency`

where `efficiency = min(1, 40 ÷ answered questions)`.

A fully correct run completed in 40 or fewer question attempts can earn 100%; more attempts reduce the efficiency component, and incorrect answers reduce accuracy. This is a configurable starter rule, not a validated assessment standard. Current scores are saved when a player reaches square 100.

## Important production notes
- This is a starter app, not a security-audited production system. Before use with real student records, configure a strong secret, HTTPS, database backups, access controls, and a privacy/retention policy.
- Admin user creation is controlled by environment variables at startup. If the admin already exists, changing the environment password does not reset it; use a password-reset workflow before wider deployment.
- The app currently uses periodic browser refresh rather than a realtime socket connection.
- For a live classroom session, test the full flow with 2–4 separate accounts and browsers before sharing it.
- A room's players take turns in order. The room code is the invitation code; users need their own account to join.
- Questions are in `questions.json` and can be edited to match the course's exact terminology or instructor-approved difficulty.

## Files
- `app.py` — Flask routes, authentication, room/game logic, persistence
- `questions.json` — 150-question bank
- `templates/` — responsive pages
- `static/style.css` — styling
- `render.yaml` / `Procfile` — deployment configuration

