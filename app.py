import os, json, random, string
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-before-deployment")
db_url = os.environ.get("DATABASE_URL", "sqlite:///snake_ladder.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

with open(os.path.join(os.path.dirname(__file__), "questions.json"), encoding="utf-8") as f:
    QUESTION_BANK = json.load(f)
QUESTION_BY_ID = {q["id"]: q for q in QUESTION_BANK}

SNAKES = {99: 54, 70: 55, 52: 42, 25: 2, 95: 72, 62: 18}
LADDERS = {4: 14, 9: 31, 20: 38, 28: 84, 40: 59, 63: 81, 71: 91}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(8), unique=True, nullable=False)
    host_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(20), default="waiting")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    host = db.relationship("User", foreign_keys=[host_id])

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("room.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    position = db.Column(db.Integer, default=0)
    turn_order = db.Column(db.Integer, nullable=False)
    questions_seen = db.Column(db.Text, default="[]")
    correct = db.Column(db.Integer, default=0)
    answered = db.Column(db.Integer, default=0)
    extra_questions = db.Column(db.Integer, default=0)
    finished = db.Column(db.Boolean, default=False)
    final_score = db.Column(db.Float, default=0)
    user = db.relationship("User")
    room = db.relationship("Room", backref=db.backref("players", lazy=True, cascade="all, delete-orphan"))

class GameState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("room.id"), unique=True, nullable=False)
    current_turn = db.Column(db.Integer, default=0)
    pending_question_id = db.Column(db.Integer, nullable=True)
    pending_player_id = db.Column(db.Integer, nullable=True)
    pending_roll = db.Column(db.Integer, nullable=True)
    last_message = db.Column(db.String(255), default="Room created. Add players and start.")
    room = db.relationship("Room")

class ScoreRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_code = db.Column(db.String(8), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    score = db.Column(db.Float, nullable=False)
    correct = db.Column(db.Integer, nullable=False)
    answered = db.Column(db.Integer, nullable=False)
    turns = db.Column(db.Integer, nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    skill_summary = db.Column(db.Text, default="{}")

def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u or not u.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def new_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not Room.query.filter_by(code=code).first():
            return code

def player_for(room, user):
    return Player.query.filter_by(room_id=room.id, user_id=user.id).first()

def room_state(room):
    state = GameState.query.filter_by(room_id=room.id).first()
    players = sorted(room.players, key=lambda p: p.turn_order)
    return state, players

def public_game(room):
    state, players = room_state(room)
    return {
        "room": room.code, "status": room.status,
        "current_turn": state.current_turn if state else 0,
        "message": state.last_message if state else "",
        "pending": bool(state and state.pending_question_id),
        "players": [{
            "username": p.user.username, "position": p.position,
            "turn_order": p.turn_order, "correct": p.correct, "answered": p.answered,
            "finished": p.finished, "score": round(p.final_score, 2)
        } for p in players],
        "snakes": SNAKES, "ladders": LADDERS
    }

@app.route("/")
def index():
    return render_template("index.html", user=current_user())

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(username) < 3 or len(username) > 80 or len(password) < 8:
            flash("Use a username of 3–80 characters and a password of at least 8 characters.")
        elif User.query.filter_by(username=username).first():
            flash("That username is already registered.")
        else:
            user = User(username=username, password_hash=generate_password_hash(password))
            db.session.add(user); db.session.commit()
            session["user_id"] = user.id
            flash("Account created. You can now create or join a room.")
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username", "").strip()).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            session.clear(); session["user_id"] = user.id
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid username or password.")
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    my_players = Player.query.filter_by(user_id=user.id).order_by(Player.id.desc()).limit(12).all()
    rooms = []
    for p in my_players:
        if p.room and p.room not in rooms:
            rooms.append(p.room)
    return render_template("dashboard.html", user=user, rooms=rooms)

@app.route("/rooms/create", methods=["POST"])
@login_required
def create_room():
    user = current_user()
    room = Room(code=new_code(), host_id=user.id)
    db.session.add(room); db.session.flush()
    db.session.add(Player(room_id=room.id, user_id=user.id, turn_order=0))
    db.session.add(GameState(room_id=room.id))
    db.session.commit()
    return redirect(url_for("game", code=room.code))

@app.route("/rooms/join", methods=["POST"])
@login_required
def join_room():
    code = request.form.get("code", "").strip().upper()
    room = Room.query.filter_by(code=code).first()
    if not room:
        flash("Room code not found."); return redirect(url_for("dashboard"))
    if room.status != "waiting":
        flash("This game has already started."); return redirect(url_for("dashboard"))
    if player_for(room, current_user()):
        return redirect(url_for("game", code=room.code))
    if len(room.players) >= 4:
        flash("This room already has four players."); return redirect(url_for("dashboard"))
    db.session.add(Player(room_id=room.id, user_id=current_user().id, turn_order=len(room.players)))
    db.session.commit()
    return redirect(url_for("game", code=room.code))

@app.route("/game/<code>")
@login_required
def game(code):
    room = Room.query.filter_by(code=code.upper()).first_or_404()
    p = player_for(room, current_user())
    if not p and room.status == "waiting" and len(room.players) < 4:
        p = Player(room_id=room.id, user_id=current_user().id, turn_order=len(room.players))
        db.session.add(p); db.session.commit()
    if not p:
        flash("You are not a player in this room.")
        return redirect(url_for("dashboard"))
    return render_template("game.html", user=current_user(), room=room, me=p)

@app.route("/api/room/<code>")
@login_required
def api_room(code):
    room = Room.query.filter_by(code=code.upper()).first_or_404()
    if not player_for(room, current_user()) and not current_user().is_admin:
        abort(403)
    return jsonify(public_game(room))

@app.route("/api/room/<code>/start", methods=["POST"])
@login_required
def start_game(code):
    room = Room.query.filter_by(code=code.upper()).first_or_404()
    if room.host_id != current_user().id: abort(403)
    if room.status != "waiting": return jsonify({"error":"Game has already started."}), 400
    if len(room.players) < 1: return jsonify({"error":"At least one player is required."}), 400
    room.status = "playing"
    state = GameState.query.filter_by(room_id=room.id).first()
    state.current_turn = 0
    state.last_message = "Game started. Roll the dice on your turn."
    db.session.commit()
    return jsonify(public_game(room))

@app.route("/api/room/<code>/roll", methods=["POST"])
@login_required
def roll(code):
    room = Room.query.filter_by(code=code.upper()).first_or_404()
    me = player_for(room, current_user())
    state, players = room_state(room)
    if room.status != "playing": return jsonify({"error":"Game has not started."}), 400
    if state.pending_question_id: return jsonify({"error":"Answer the current question first."}), 400
    active = next((p for p in players if not p.finished and p.turn_order >= state.current_turn), None)
    if active is None:
        active = next((p for p in players if not p.finished), None)
        if active: state.current_turn = active.turn_order
    if not active or active.id != me.id:
        return jsonify({"error":"It is not your turn."}), 403
    roll_value = random.randint(1, 6)
    target = me.position + roll_value
    if target > 100:
        state.pending_roll = 0
        state.pending_player_id = me.id
        me.extra_questions += 1
        qid = choose_question(me)
        state.pending_question_id = qid
        state.last_message = f"{me.user.username} rolled {roll_value}; exact 100 required, so answer a practice question."
    else:
        state.pending_roll = roll_value
        state.pending_player_id = me.id
        me.extra_questions += 1
        qid = choose_question(me)
        state.pending_question_id = qid
        state.last_message = f"{me.user.username} rolled {roll_value}; answer the Python question to move."
    db.session.commit()
    return jsonify({"question": public_question(QUESTION_BY_ID[qid]), "game": public_game(room)})

def choose_question(player):
    seen = set(json.loads(player.questions_seen or "[]"))
    available = [q for q in QUESTION_BANK if q["id"] not in seen]
    if not available:
        # After all 150 are seen, permit reuse but prefer questions not asked recently.
        available = QUESTION_BANK[:]
    q = random.choice(available)
    seen.add(q["id"])
    player.questions_seen = json.dumps(list(seen))
    return q["id"]

def public_question(q):
    return {k:q[k] for k in ("id","topic","difficulty","question","choices")}

@app.route("/api/room/<code>/answer", methods=["POST"])
@login_required
def answer(code):
    room = Room.query.filter_by(code=code.upper()).first_or_404()
    me = player_for(room, current_user())
    state, players = room_state(room)
    if not state.pending_question_id or state.pending_player_id != me.id:
        return jsonify({"error":"There is no question waiting for you."}), 400
    data = request.get_json(silent=True) or {}
    try: selected = int(data.get("choice"))
    except (ValueError, TypeError): return jsonify({"error":"Select an answer."}), 400
    q = QUESTION_BY_ID[state.pending_question_id]
    me.answered += 1
    correct = selected == q["answer"]
    if correct:
        me.correct += 1
        if state.pending_roll and state.pending_roll > 0:
            target = me.position + state.pending_roll
            if target <= 100:
                if target in LADDERS: target = LADDERS[target]
                elif target in SNAKES: target = SNAKES[target]
                me.position = target
        if me.position == 100:
            me.finished = True
            room.status = "finished" if all(p.finished for p in players if p.id != me.id) else room.status
    state.pending_question_id = None
    state.pending_player_id = None
    state.pending_roll = None
    if me.finished:
        state.last_message = f"{me.user.username} reached square 100! Final score: {score_for(me):.2f}%."
        me.final_score = score_for(me)
        db.session.add(ScoreRecord(room_code=room.code, username=me.user.username,
            score=me.final_score, correct=me.correct, answered=me.answered,
            turns=me.answered, skill_summary=json.dumps({"topics_seen": topics_for(me)})))
    else:
        state.last_message = f"{me.user.username} answered {'correctly' if correct else 'incorrectly'}. " + (
            "Correct answer: " + q["choices"][q["answer"]] + ". " + q["explanation"] if not correct else "Move completed."
        )
        next_player = next((p for p in players if p.turn_order > me.turn_order and not p.finished), None)
        if next_player is None:
            next_player = next((p for p in players if not p.finished), None)
        state.current_turn = next_player.turn_order if next_player else me.turn_order
    db.session.commit()
    return jsonify({"correct":correct, "correct_index":q["answer"], "explanation":q["explanation"],
                    "game":public_game(room)})

def score_for(player):
    # Accuracy is multiplied by a question-efficiency factor. A perfect optimal run
    # (all correct, no extra questions beyond the required one per move) earns 100.
    if player.answered == 0: return 0.0
    accuracy = player.correct / player.answered
    # Baseline: 40 question attempts for a full-length board run. More attempts
    # reduce efficiency; a fully correct run completed in 40 or fewer questions
    # can earn 100%.
    efficiency = min(1.0, 40 / player.answered)
    return round(100 * accuracy * efficiency, 2)

def topics_for(player):
    seen = set(json.loads(player.questions_seen or "[]"))
    return sorted({QUESTION_BY_ID[i]["topic"] for i in seen if i in QUESTION_BY_ID})

@app.route("/admin")
@login_required
@admin_required
def admin():
    records = ScoreRecord.query.order_by(ScoreRecord.completed_at.desc()).limit(500).all()
    users = User.query.count()
    rooms = Room.query.count()
    return render_template("admin.html", records=records, users=users, rooms=rooms, user=current_user())

@app.route("/admin/export.csv")
@login_required
@admin_required
def export_csv():
    import csv, io
    from flask import Response
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["room_code","username","score_percent","correct","answered","turns","completed_at","skill_summary"])
    for r in ScoreRecord.query.order_by(ScoreRecord.completed_at.desc()).all():
        writer.writerow([r.room_code,r.username,r.score,r.correct,r.answered,r.turns,r.completed_at.isoformat(),r.skill_summary])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename=python_snake_ladder_scores.csv"})

with app.app_context():
    db.create_all()
    # First-time admin creation is controlled by environment variables.
    admin_name = os.environ.get("ADMIN_USERNAME")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if admin_name and admin_password and not User.query.filter_by(username=admin_name).first():
        db.session.add(User(username=admin_name, password_hash=generate_password_hash(admin_password), is_admin=True))
        db.session.commit()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
