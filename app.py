# python
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import os
import json
from datetime import timedelta

app = Flask(__name__)
app.secret_key = "your_secret_key"  
# Make sessions permanent by default lifetime (user will remain logged in if session cookie persists)
app.permanent_session_lifetime = timedelta(days=30)
DB_PATH = "flask_login.db"

# -----------------------------
# Database helpers
# -----------------------------
def ensure_db_path():
    global DB_PATH
    base_dir = os.path.dirname(__file__)
    if not os.path.isabs(DB_PATH):
        DB_PATH = os.path.join(base_dir, DB_PATH)
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

def get_db_connection():
    ensure_db_path()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Create the SQLite file and run schema.sql (idempotent).
    Clean up duplicate topics (case-insensitive) and enforce a UNIQUE index on title (NOCASE)
    so the topics page shows one box per subject.
    """
    ensure_db_path()
    base_dir = os.path.dirname(__file__)
    schema_file = os.path.join(base_dir, "schema.sql")
    conn = sqlite3.connect(DB_PATH)
    try:
        if os.path.exists(schema_file):
            with open(schema_file, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            # Remove duplicate topics (keep lowest id) based on case-insensitive title
            try:
                conn.execute(
                    "DELETE FROM topics WHERE id NOT IN (SELECT MIN(id) FROM topics GROUP BY LOWER(title));"
                )
            except Exception:
                # If LOWER isn't supported for grouping in the user's SQLite version, try simpler grouping
                try:
                    conn.execute(
                        "DELETE FROM topics WHERE id NOT IN (SELECT MIN(id) FROM topics GROUP BY title);"
                    )
                except Exception:
                    pass
            # Create a case-insensitive unique index on title to prevent future duplicates
            try:
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_topics_title_nocase ON topics(title COLLATE NOCASE);")
            except Exception:
                # ignore if the index cannot be created
                pass
            conn.commit()
    finally:
        conn.close()

# -----------------------------
# External Data Import (Local JSON file)
# -----------------------------
def fetch_libraries():
    """
    Read `libraries-information-location.json` in the project dir and
    normalize records to dicts with keys: name, address, lat, lon.
    """
    base_dir = os.path.dirname(__file__)
    candidates = [
        os.path.join(base_dir, "libraries-information-location.json"),
        os.path.join(base_dir, "data", "libraries-information-location.json"),
    ]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if not path:
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []

    libs = []
    if isinstance(raw, list):
        for item in raw:
            name = item.get("name") or item.get("library_name")
            address = item.get("address") or item.get("addr") or ""
            lat = item.get("lat") or item.get("latitude")
            lon = item.get("lon") or item.get("lng") or item.get("longitude")
            # some files use `lng` (as in provided JSON)
            if lon is None and "lng" in item:
                lon = item.get("lng")
            if name and address:
                libs.append({"name": name.strip(), "address": address.strip(), "lat": lat, "lon": lon})
    elif isinstance(raw, dict):
        # try common keys
        records = raw.get("records") or raw.get("results") or raw.get("data")
        if isinstance(records, list):
            for rec in records:
                fields = rec.get("fields") if isinstance(rec, dict) and "fields" in rec else rec
                if not isinstance(fields, dict):
                    continue
                name = fields.get("name") or fields.get("library_name")
                address = fields.get("address") or fields.get("addr") or ""
                lat = fields.get("lat") or fields.get("latitude")
                lon = fields.get("lon") or fields.get("lng") or fields.get("longitude")
                if name and address:
                    libs.append({"name": name.strip(), "address": address.strip(), "lat": lat, "lon": lon})
    return libs

def seed_libraries():
    """
    Insert libraries into locations table; avoid duplicates by name+address.
    """
    libs = fetch_libraries()
    if not libs:
        return
    db = get_db_connection()
    inserted = 0
    try:
        for lib in libs:
            name = lib.get("name") or ""
            address = lib.get("address") or ""
            lat = lib.get("lat")
            lon = lib.get("lon")
            if not name or not address:
                continue
            existing = db.execute(
                "SELECT id FROM locations WHERE name = ? AND address = ?",
                (name, address)
            ).fetchone()
            if existing:
                # update coords if missing
                db.execute(
                    "UPDATE locations SET lat = COALESCE(lat, ?), lon = COALESCE(lon, ?) WHERE id = ?",
                    (lat, lon, existing["id"])
                )
                continue
            db.execute(
                "INSERT INTO locations (name, address, lat, lon) VALUES (?, ?, ?, ?)",
                (name, address, lat, lon)
            )
            inserted += 1
        db.commit()
    finally:
        db.close()

# -----------------------------
# Routes
# -----------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        db = get_db_connection()
        user = db.execute(
            "SELECT * FROM users WHERE username = ? AND email = ? AND password = ?",
            (username, email, password)
        ).fetchone()
        db.close()
        if user:
            # persist the session so the cookie remains valid across browser restarts
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid credentials"
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if not username or not email or not password:
            error = "All fields required"
        else:
            db = get_db_connection()
            exists = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                error = "Email already registered"
                db.close()
            else:
                db.execute(
                    "INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                    (username, password, email)
                )
                db.commit()
                user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
                db.close()
                # make session persistent after registering
                session.permanent = True
                session['user_id'] = user['id']
                session['username'] = username
                return redirect(url_for('dashboard'))
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    db = get_db_connection()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    db.close()
    username = user['username'] if user else session.get('username')
    email = user['email'] if user else ""
    return render_template('dashboard.html', username=username, email=email)

@app.route('/notes', methods=['GET', 'POST'])
def notes():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    # Handle form submission using PRG to prevent duplicate inserts / looping boxes
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if content:
            db = get_db_connection()
            db.execute("INSERT INTO notes (user_id, content) VALUES (?, ?)", (session['user_id'], content))
            db.commit()
            db.close()
        return redirect(url_for('notes'))

    # GET: show notes
    db = get_db_connection()
    rows = db.execute("SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC", (session['user_id'],)).fetchall()
    db.close()
    notes_list = [dict(r) for r in rows]
    return render_template('notes.html', notes=notes_list)

@app.route('/delete_note/<int:note_id>', methods=['POST'])
def delete_note(note_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    db = get_db_connection()
    note = db.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, session['user_id'])).fetchone()
    if note:
        db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        db.commit()
    db.close()
    return redirect(url_for('notes'))

@app.route('/topics')
def topics():
    db = get_db_connection()
    rows = db.execute("SELECT id, title, description FROM topics ORDER BY id").fetchall()
    db.close()
    topics_list = [dict(r) for r in rows]

    # Map common synonyms to canonical topic titles
    canonical_map = {
        'maths': 'Mathematics', 'math': 'Mathematics', 'mathematics': 'Mathematics',
        'science': 'Science', 'sci': 'Science',
        'literature': 'Literature', 'lit': 'Literature', 'english': 'Literature',
        'history': 'History', 'hist': 'History'
    }

    # Default descriptions when source row doesn't provide one
    defaults = {
        'Mathematics': 'Core mathematics topics: algebra, calculus, statistics.',
        'Science': 'Fundamental science topics: physics, chemistry, biology.',
        'Literature': 'Analysis and interpretation of prose and poetry.',
        'History': 'Key events and themes across history.'
    }

    seen = set()
    unique_topics = []
    for t in topics_list:
        raw_title = (t.get('title') or '').strip()
        key = raw_title.lower()
        canonical = canonical_map.get(key, None)
        if canonical is None:
            # Use title-cased version of whatever title is present if not in map
            canonical = raw_title.title() if raw_title else raw_title
        # Skip duplicates by canonical title (case-insensitive)
        if canonical.lower() in seen:
            continue
        seen.add(canonical.lower())
        desc = t.get('description') if t.get('description') else defaults.get(canonical, '')
        unique_topics.append({ 'id': t.get('id'), 'title': canonical, 'description': desc })

    return render_template('topics.html', topics=unique_topics)

@app.route('/topic/<int:topic_id>')
def view_topic(topic_id):
    db = get_db_connection()
    topic = db.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
    if topic is None:
        db.close()
        return "Topic not found", 404
    sections = db.execute("SELECT title, content FROM topic_sections WHERE topic_id = ? ORDER BY id", (topic_id,)).fetchall()
    revision = db.execute("SELECT title, content FROM revision_sheets WHERE topic_id = ? ORDER BY id", (topic_id,)).fetchall()
    db.close()
    sections_list = [dict(s) for s in sections]
    revision_list = [dict(r) for r in revision]
    return render_template('view_topic.html', topic=dict(topic), sections=sections_list, revision=revision_list)

# -----------------------------
# Locations (Map)
# -----------------------------
@app.route('/locations')
def locations():
    format_param = request.args.get('format', '').lower()
    db = get_db_connection()
    rows = db.execute("SELECT id, name, address, lat, lon FROM locations ORDER BY id").fetchall()
    db.close()
    locations_list = [dict(r) for r in rows]
    if format_param == "json":
        # normalize numeric types (ensure floats or None)
        for loc in locations_list:
            try:
                loc['lat'] = float(loc['lat']) if loc['lat'] is not None else None
                loc['lon'] = float(loc['lon']) if loc['lon'] is not None else None
            except Exception:
                loc['lat'], loc['lon'] = None, None
    return render_template('locations.html', locations=locations_list, suburb="")

def api_locations():
    db = get_db_connection()
    rows = db.execute("SELECT id, name, address, lat, lon FROM locations ORDER BY id").fetchall()
    db.close()
    locations_list = [dict(r) for r in rows]
    return jsonify(locations_list)

# New: richer location data for the map popups
@app.route('/api/locations_full')
def api_locations_full():
    """Return detailed location info (try local JSON first, otherwise DB rows).
    Fields: name, address, lat, lon, hours, wheelchair_accessible, meeting_rooms, website
    """
    base_dir = os.path.dirname(__file__)
    json_path = os.path.join(base_dir, "libraries-information-location.json")
    results = []

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []

        if isinstance(data, list):
            for item in data:
                lat = item.get("lat") or item.get("latitude")
                lon = item.get("lng") if item.get("lng") is not None else item.get("lon") or item.get("longitude")
                results.append({
                    "name": item.get("name"),
                    "address": item.get("address"),
                    "lat": lat,
                    "lon": lon,
                    "hours": item.get("hours"),
                    "wheelchair_accessible": item.get("wheelchair_accessible"),
                    "meeting_rooms": item.get("meeting_rooms"),
                    "website": item.get("website")
                })
            # filter out entries without coords
            results = [r for r in results if r.get("lat") is not None and r.get("lon") is not None]
            return jsonify(results)

    # Fallback: read from DB and return minimal fields
    db = get_db_connection()
    rows = db.execute("SELECT id, name, address, lat, lon FROM locations ORDER BY id").fetchall()
    db.close()
    for r in rows:
        results.append({
            "name": r["name"],
            "address": r["address"],
            "lat": r["lat"],
            "lon": r["lon"],
            "hours": None,
            "wheelchair_accessible": None,
            "meeting_rooms": None,
            "website": None
        })
    return jsonify(results)

# -----------------------------
# App startup
# -----------------------------
if __name__ == "__main__":
    init_db()          # ensure tables and seeds exist
    seed_libraries()   # load libraries from local JSON file
    print(">>> Starting Flask server on http://127.0.0.1:5001/")
    app.run(debug=True, port=5001)
