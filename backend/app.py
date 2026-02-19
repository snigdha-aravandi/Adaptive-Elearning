import sqlite3
import sys
import os
import re
from datetime import datetime
from flask_cors import CORS
from flask import Flask, jsonify, g, request, session, redirect, render_template, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

 # Import CORS to allow cross-origin requests

# ===============================
# Validation Utilities
# ===============================

def validate_email(email):
    """RFC 5322 compliant email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """
    Password must have:
    - Min 8 characters
    - 1 uppercase
    - 1 lowercase  
    - 1 number
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    return True, "Valid"

# Add the parent directory to sys.path so we can import the ml module
# This is necessary because 'ml' is outside the 'backend' folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from ml.path_generator import recommend_next_step
    from ml.difficulty_predictor import predictor
except ImportError as e:
    print(f"Warning: Could not import ml modules. Error: {e}")
    # Define dummy functions if import fails to prevent crash
    def recommend_next_step(data):
        return "Error", "Could not load logic"
    predictor = None

# Initialize the Flask application
app = Flask(__name__)
app.secret_key = "dev-secret-key"   # needed later for login sessions
CORS(app)


# ===============================
# Database Configuration
# ===============================

DATABASE = "database/database.db"

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()
# ===============================
# Database Initialization
# ===============================

def init_db():
    db = sqlite3.connect(DATABASE)
    with open("database/schema.sql", "r") as f:
        db.executescript(f.read())
    db.close()
    print("Database initialized.")
def login_required():
    if "user_id" not in session:
        return False
    return True

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        if session.get("role") != "admin":
            flash("Access denied: Administrator privileges required.")
            return redirect("/dashboard")
        return f(*args, **kwargs)
    return decorated_function


# --- Routes ---

# 1. Home Route
@app.route('/')
def home():
    if "user_id" in session:
        return redirect("/dashboard")
    return render_template("index.html")
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")
    
    data = request.json
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")

    # Validation
    if not name or len(name) < 2:
        return jsonify({"error": "Name must be at least 2 characters"}), 400
    
    if not validate_email(email):
        return jsonify({"error": "Invalid email format"}), 400
    
    is_valid, msg = validate_password(password)
    if not is_valid:
        return jsonify({"error": msg}), 400

    db = get_db()
    
    # Check for duplicate
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return jsonify({"error": "Email already registered"}), 400
    
    try:
        db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password, method='pbkdf2:sha256'))
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Registration failed"}), 500

    return jsonify({"message": "Account created successfully"})

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        
        if not email or not password:
            return render_template("login.html", error="Email and password required")
        
        if not validate_email(email):
            return render_template("login.html", error="Invalid email format")
        
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["email"] = user["email"]
            session["role"] = user["role"] if "role" in user.keys() else "student"
            return redirect("/dashboard")
        
        return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")




@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("dashboard.html")
from flask import render_template

@app.route("/learn/<topic>")
def learn_topic(topic):
    """
    Renders the quiz interface for a specific topic.
    Uses ML-based difficulty prediction if available.
    """
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    topic_row = db.execute("SELECT id FROM topics WHERE name = ?", (topic,)).fetchone()
    if not topic_row:
        return "Invalid topic", 404
    
    # ML-BASED DIFFICULTY RECOMMENDATION
    suggested_difficulty = 'easy'  # default fallback
    if predictor:
        try:
            suggested_difficulty = predictor.predict_difficulty(
                session["user_id"], 
                topic_row["id"]
            )
        except Exception as e:
            print(f"ML prediction failed: {e}, using default")
            suggested_difficulty = 'easy'

    # Render quiz template with ML suggestion
    return render_template("quiz.html", topic=topic, suggested_difficulty=suggested_difficulty)

@app.route("/quiz/availability/<topic>", methods=["GET"])
def check_quiz_availability(topic):
    """
    Checks if the user has enough unused questions to start a quiz
    for each difficulty level.
    """
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()
    topic_row = db.execute("SELECT id FROM topics WHERE name = ?", (topic,)).fetchone()
    if not topic_row:
        return jsonify({"error": "Invalid topic"}), 404
        
    topic_id = topic_row["id"]
    user_id = session["user_id"]
    
    availability = {}
    REQUIRED_MIN = 5
    
    # Check for each difficulty level
    for level_name, level_code in [("easy", 1), ("medium", 2), ("hard", 3)]:
        # 1. Count Total Questions in Bank
        total_count = db.execute(
            "SELECT COUNT(*) FROM quiz_questions WHERE topic_id = ? AND difficulty = ?",
            (topic_id, level_code)
        ).fetchone()[0]
        
        # 2. Count Used Questions by User
        used_count = db.execute(
            """
            SELECT COUNT(DISTINCT qr.question_id)
            FROM question_responses qr
            JOIN quiz_attempts qa ON qr.attempt_id = qa.id
            WHERE qa.user_id = ? AND qa.topic_id = ? AND qr.question_id IN (
                SELECT id FROM quiz_questions WHERE difficulty = ?
            )
            """,
            (user_id, topic_id, level_code)
        ).fetchone()[0]
        
        available_count = total_count - used_count
        
        availability[level_name] = {
            "status": "available" if available_count >= REQUIRED_MIN else "unavailable",
            "available_count": available_count,
            "required": REQUIRED_MIN
        }
        
    return jsonify(availability)

@app.route("/quiz/start", methods=["POST"])
def start_quiz():
    """
    Starts a new quiz attempt and returns questions.
    """
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    topic_name = data.get("topic")
    difficulty_str = data.get("difficulty", "easy") # default to easy
    
    db = get_db()
    topic_row = db.execute("SELECT id FROM topics WHERE name = ?", (topic_name,)).fetchone()
    
    if not topic_row:
        return jsonify({"error": "Invalid topic"}), 400
        
    topic_id = topic_row["id"]
    user_id = session["user_id"]
    
    # Map difficulty string to integer level in DB
    diff_map = {"easy": 1, "medium": 2, "hard": 3}
    diff_level = diff_map.get(difficulty_str, 1)
    
    db = get_db()
    
    # 1. Create a new attempt record
    cursor = db.execute(
        """
        INSERT INTO quiz_attempts (user_id, topic_id, attempt_difficulty, status)
        VALUES (?, ?, ?, 'started')
        """,
        (user_id, topic_id, difficulty_str)
    )
    attempt_id = cursor.lastrowid
    
    # 2. Fetch history: Questions already answered by this user for this topic
    used_rows = db.execute(
        """
        SELECT DISTINCT qr.question_id
        FROM question_responses qr
        JOIN quiz_attempts qa ON qr.attempt_id = qa.id
        WHERE qa.user_id = ? AND qa.topic_id = ?
        """,
        (user_id, topic_id)
    ).fetchall()
    
    used_ids = [row["question_id"] for row in used_rows]
    
    # 3. Select Questions (Priority: Unused, Specific Difficulty)
    questions = []
    
    if used_ids:
        placeholders = ','.join(['?'] * len(used_ids))
        query_unused = f"""
            SELECT DISTINCT id, question, question_type, option_a, option_b, option_c, option_d 
            FROM quiz_questions 
            WHERE topic_id = ? AND difficulty = ?
            AND id NOT IN ({placeholders})
            ORDER BY RANDOM()
            LIMIT 5
        """
        params_unused = [topic_id, diff_level] + used_ids
        questions = db.execute(query_unused, params_unused).fetchall()
        questions = [dict(q) for q in questions]
    else:
        query_unused = """
            SELECT DISTINCT id, question, question_type, option_a, option_b, option_c, option_d 
            FROM quiz_questions 
            WHERE topic_id = ? AND difficulty = ?
            ORDER BY RANDOM()
            LIMIT 5
        """
        questions = db.execute(query_unused, (topic_id, diff_level)).fetchall()
        questions = [dict(q) for q in questions]
    
    # 4. STRICT Check: If insufficient unused questions, return status, DO NOT FALLBACK
    if len(questions) < 5:
        # Return strict status for frontend to handle
        return jsonify({
            "status": "INSUFFICIENT_QUESTIONS",
            "required": 5,
            "available": len(questions),
            "topic": topic_name,
            "difficulty": difficulty_str
        }), 400

    db.commit()
    
    return jsonify({
        "status": "OK",
        "attempt_id": attempt_id,
        "questions": questions
    })

@app.route("/quiz/submit", methods=["POST"])
def submit_quiz():
    """
    Calculates score and saves individual question responses.
    """
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    attempt_id = data.get("attempt_id")
    responses = data.get("responses") # List of {question_id: X, selected: Y}
    
    if not attempt_id or not responses:
        return jsonify({"error": "Missing submission data"}), 400
    
    db = get_db()
    
    # 1. Verify attempt ownership and status
    attempt = db.execute(
        "SELECT * FROM quiz_attempts WHERE id = ? AND user_id = ?",
        (attempt_id, session["user_id"])
    ).fetchone()
    
    if not attempt:
        return jsonify({"error": "Invalid attempt"}), 403
    
    if attempt["status"] == "completed":
        return jsonify({"error": "Attempt already submitted"}), 400

    # 2. Score the attempt
    correct_count = 0
    total_count = len(responses)
    
    from datetime import datetime
    
    for resp in responses:
        q_id = resp.get("question_id")
        selected = resp.get("selected")
        
        # Fetch question details from DB
        q_row = db.execute(
            "SELECT question_type, correct_answer FROM quiz_questions WHERE id = ?", 
            (q_id,)
        ).fetchone()
        
        if not q_row:
            continue
            
        q_type = q_row["question_type"]
        correct_answer = q_row["correct_answer"]
        
        # STRICT EVALUATION RULES
        is_correct = False
        if q_type == 'mcq':
            # MCQ: Exact string match
            is_correct = (str(selected) == str(correct_answer))
        elif q_type == 'code':
            # CODE: Exact stripped match
            is_correct = (str(selected).strip() == str(correct_answer).strip())
            
        if is_correct:
            correct_count += 1
            
        # Record granular response
        db.execute(
            """
            INSERT INTO question_responses (attempt_id, question_id, selected_option, is_correct)
            VALUES (?, ?, ?, ?)
            """,
            (attempt_id, q_id, selected, is_correct)
        )

    final_score = (correct_count / total_count * 100) if total_count > 0 else 0
    
    # 3. Finalize attempt in quiz_attempts
    # We use CURRENT_TIMESTAMP for end_time
    db.execute(
        """
        UPDATE quiz_attempts 
        SET final_score = ?, end_time = CURRENT_TIMESTAMP, status = 'completed'
        WHERE id = ?
        """,
        (final_score, attempt_id)
    )

    # 4. RULE-BASED MASTERY UPDATE
    # Fetch the finalized attempt to get start/end times and difficulty for calculations
    attempt_final = db.execute(
        "SELECT *, (strftime('%s', end_time) - strftime('%s', start_time)) as duration FROM quiz_attempts WHERE id = ?", 
        (attempt_id,)
    ).fetchone()
    
    topic_id = attempt_final["topic_id"]
    difficulty = attempt_final["attempt_difficulty"]
    duration_seconds = attempt_final["duration"] or 0
    
    # Rule A: Normalize the raw quiz score (0-100) to a 0.0-1.0 range
    normalized_score = final_score / 100
    
    # Rule B: Apply Difficulty Caps
    # These caps ensure that a student cannot reach 100% mastery by only taking easy tests.
    # Academic Rationale: Higher proficiency levels require demonstrated success at higher difficulties.
    diff_caps = {"easy": 0.5, "medium": 0.8, "hard": 1.0}
    cap = diff_caps.get(difficulty, 0.5)
    
    target_mastery = normalized_score * cap
    
    # Rule C: Update student_progress (Deterministic & Persistant)
    # We ensure a row exists first
    db.execute(
        "INSERT OR IGNORE INTO student_progress (user_id, topic_id, mastery, attempts, time_spent) VALUES (?, ?, 0.0, 0, 0)",
        (session["user_id"], topic_id)
    )
    
    # Rule D: Mastery Persistence
    # Mastery NEVER decreases. If a student performs poorly on a later attempt, 
    # their recorded 'highest competence' remains.
    db.execute(
        """
        UPDATE student_progress
        SET 
            mastery = MAX(mastery, ?),
            attempts = attempts + 1,
            time_spent = time_spent + ?
        WHERE user_id = ? AND topic_id = ?
        """,
        (target_mastery, duration_seconds // 60, session["user_id"], topic_id)
    )
    
    db.commit()
    
    return jsonify({
        "message": "Quiz submitted successfully",
        "score": final_score,
        "correct": correct_count,
        "total": total_count,
        "new_mastery": target_mastery
    })

@app.route("/learning-path")
def learning_path():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    user_id = session["user_id"]
    db = get_db()
    
    all_topics = db.execute("SELECT id, name FROM topics").fetchall()
    mastery_map = {row["name"]: 0.0 for row in all_topics}
    topic_id_to_name = {row["id"]: row["name"] for row in all_topics}

    rows = db.execute(
        "SELECT topic_id, mastery FROM student_progress WHERE user_id=?",
        (user_id,)
    ).fetchall()

    for row in rows:
        if row["topic_id"] in topic_id_to_name:
            mastery_map[topic_id_to_name[row["topic_id"]]] = row["mastery"]

    # 🔥 CORE CHANGE: reorder by mastery
    sorted_topics = sorted(
        mastery_map.items(),
        key=lambda x: x[1]  # lowest mastery first
    )

    path = []
    for topic, mastery in sorted_topics:
        # Determine logical status and explanation
        db = get_db()
        # Get attempts and prerequisite info
        stats = db.execute("""
            SELECT 
                (SELECT COUNT(*) FROM quiz_attempts WHERE user_id = ? AND topic_id = (SELECT id FROM topics WHERE name = ?)) as attempts,
                (SELECT name FROM topics WHERE id = (SELECT prerequisite_id FROM topics WHERE name = ?)) as prereq_name,
                (SELECT mastery FROM student_progress WHERE user_id = ? AND topic_id = (SELECT prerequisite_id FROM topics WHERE name = ?)) as prereq_mastery
            """, (user_id, topic, topic, user_id, topic)).fetchone()

        # --- SAFE DEFAULTS (MANDATORY) ---
        status = "locked"
        explanation = "Locked due to unmet prerequisite."

        # --- ENFORCE PREREQUISITE FIRST ---
        if stats["prereq_name"] and (stats["prereq_mastery"] is None or stats["prereq_mastery"] < 0.7):
            status = "locked"
            explanation = f"Locked. Complete {stats['prereq_name']} first."
        else:
            # Prerequisite satisfied
            if mastery >= 0.7:
                status = "completed"
                explanation = "Mastery achieved. Concepts fully unlocked."
            elif mastery > 0:
                status = "current"
                explanation = "Revision required. Practice to reach 70% mastery."
            else:
                status = "priority"
                explanation = "Prerequisite met. Focus here to progress."

        path.append({
            "topic": topic,
            "mastery": mastery,
            "status": status,
            "explanation": explanation
        })

    return jsonify(path)
    
@app.route("/content/<topic>")
def content_page(topic):
    """
    Renders the learning content for a specific topic.
    Fetches structured content and prerequisite metadata from the database.
    """
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    
    # 1. Fetch topic, prerequisite, and content in a single consolidated query
    # We join topics (t) with itself (p) to get the name of the prerequisite
    # and with topic_content (tc) to get the instructional material.
    query = """
        SELECT 
            t.id as id,
            t.name as topic_name,
            p.name as prereq_name,
            tc.content_title,
            tc.explanation_md,
            tc.code_sample,
            tc.youtube_url,
            tc.reference_url,
            tc.metadata
        FROM topics t
        LEFT JOIN topics p ON t.prerequisite_id = p.id
        LEFT JOIN topic_content tc ON t.id = tc.topic_id
        WHERE t.name = ?
    """
    row = db.execute(query, (topic,)).fetchone()

    # 2. Handle Case: Invalid topic name
    if not row:
        return "Topic not found", 404

    # 3. Handle Case: Topic exists but topic_content is empty/missing
    if not row["explanation_md"]:
        return render_template(
            "content.html",
            topic=row["topic_name"],
            content="This module is currently being developed by the academic team. Please check back later."
        )

    # 4. Success: Pass all structured data to the template
    # Note: 'content' is passed separately for backward compatibility with the existing template.
    return render_template(
        "content.html",
        topic=row["topic_name"],
        content=row["explanation_md"],
        details={
            "title": row["content_title"],
            "code": row["code_sample"],
            "video": row["youtube_url"],
            "reference": row["reference_url"],
            "prerequisite": row["prereq_name"],
            "metadata": row["metadata"]
        }
    )

# 4. Recommendation Route
@app.route("/recommendation")
def recommendation():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    user_id = session["user_id"]
    db = get_db()

    all_topics = db.execute("SELECT id, name FROM topics").fetchall()
    student_mastery = {row["name"]: 0.0 for row in all_topics}
    topic_id_to_name = {row["id"]: row["name"] for row in all_topics}

    rows = db.execute(
        "SELECT topic_id, mastery FROM student_progress WHERE user_id=?",
        (user_id,)
    ).fetchall()

    for row in rows:
        if row["topic_id"] in topic_id_to_name:
            student_mastery[topic_id_to_name[row["topic_id"]]] = row["mastery"]

    topic, explanation = recommend_next_step(student_mastery)

    return jsonify({
        "student_mastery": student_mastery,
        "recommendation": {
            "topic": topic,
            "explanation": explanation
        }
    })


@app.route("/progress")
def get_progress():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    user_id = session["user_id"]
    db = get_db()

    all_topics = db.execute("SELECT id, name FROM topics").fetchall()
    topic_id_to_name = {row["id"]: row["name"] for row in all_topics}

    rows = db.execute(
        "SELECT topic_id, mastery FROM student_progress WHERE user_id=?",
        (user_id,)
    ).fetchall()

    progress = {}
    for row in rows:
        if row["topic_id"] in topic_id_to_name:
            progress[topic_id_to_name[row["topic_id"]]] = row["mastery"]

    return jsonify(progress)


    
@app.route("/student-analytics")
def student_analytics():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user_id = session["user_id"]
    db = get_db()
    
    # 1. Total attempts and total time from student_progress
    progress_stats = db.execute(
        "SELECT SUM(attempts) as total_attempts, SUM(time_spent) as total_time FROM student_progress WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    
    # 2. Average time per question from question_responses
    avg_q_time = db.execute("""
        SELECT AVG(qr.time_spent_seconds) as avg_time
        FROM question_responses qr
        JOIN quiz_attempts qa ON qr.attempt_id = qa.id
        WHERE qa.user_id = ?
    """, (user_id,)).fetchone()
    
    # 3. Highest difficulty attempted
    # Mapping: easy=1, medium=2, hard=3
    highest_diff = db.execute("""
        SELECT attempt_difficulty FROM quiz_attempts 
        WHERE user_id = ? AND status = 'completed'
        ORDER BY CASE attempt_difficulty 
            WHEN 'hard' THEN 3 
            WHEN 'medium' THEN 2 
            WHEN 'easy' THEN 1 
            ELSE 0 END DESC
        LIMIT 1
    """, (user_id,)).fetchone()

    # 4. Mastery per topic (already available but good to include here)
    mastery_rows = db.execute("""
        SELECT t.name, sp.mastery 
        FROM student_progress sp
        JOIN topics t ON sp.topic_id = t.id
        WHERE sp.user_id = ?
    """, (user_id,)).fetchall()

    return jsonify({
        "total_attempts": progress_stats["total_attempts"] or 0,
        "total_time_minutes": progress_stats["total_time"] or 0,
        "avg_time_per_question": round(avg_q_time["avg_time"] or 0, 1),
        "highest_difficulty": highest_diff["attempt_difficulty"] if highest_diff else "None",
        "topic_mastery": {row["name"]: row["mastery"] for row in mastery_rows}
    })


# --- Admin Routes (Read-Only) ---

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        "users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "topics": db.execute("SELECT COUNT(*) FROM topics").fetchone()[0],
        "questions": db.execute("SELECT COUNT(*) FROM quiz_questions").fetchone()[0],
        "attempts": db.execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0]
    }
    return render_template("admin/dashboard.html", stats=stats)

@app.route("/admin/compare")
@admin_required
def admin_compare():
    db = get_db()
    # Fetch all students for the dropdowns
    students = db.execute("SELECT id, name, email FROM users WHERE role = 'student'").fetchall()
    
    student_id1 = request.args.get("sid1")
    student_id2 = request.args.get("sid2")
    
    data1 = None
    data2 = None
    
    if student_id1:
        data1 = get_detailed_student_data(db, student_id1)
    if student_id2:
        data2 = get_detailed_student_data(db, student_id2)
        
    return render_template("admin/compare_students.html", students=students, data1=data1, data2=data2)

def get_detailed_student_data(db, user_id):
    # Same logic as student_analytics but for any user_id
    progress_stats = db.execute(
        "SELECT SUM(attempts) as total_attempts, SUM(time_spent) as total_time FROM student_progress WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    
    avg_q_time = db.execute("""
        SELECT AVG(qr.time_spent_seconds) as avg_time
        FROM question_responses qr
        JOIN quiz_attempts qa ON qr.attempt_id = qa.id
        WHERE qa.user_id = ?
    """, (user_id,)).fetchone()
    
    highest_diff = db.execute("""
        SELECT attempt_difficulty FROM quiz_attempts 
        WHERE user_id = ? AND status = 'completed'
        ORDER BY CASE attempt_difficulty 
            WHEN 'hard' THEN 3 
            WHEN 'medium' THEN 2 
            WHEN 'easy' THEN 1 
            ELSE 0 END DESC
        LIMIT 1
    """, (user_id,)).fetchone()

    mastery_rows = db.execute("""
        SELECT t.name, sp.mastery 
        FROM student_progress sp
        JOIN topics t ON sp.topic_id = t.id
        WHERE sp.user_id = ?
    """, (user_id,)).fetchall()

    # Get current topic recommendation
    student_mastery = {row["name"]: row["mastery"] for row in mastery_rows}
    # Ensure all topics are represented
    all_topics = db.execute("SELECT name FROM topics").fetchall()
    for t in all_topics:
        if t["name"] not in student_mastery:
            student_mastery[t["name"]] = 0.0
            
    topic, explanation = recommend_next_step(student_mastery)

    user_info = db.execute("SELECT name, email FROM users WHERE id = ?", (user_id,)).fetchone()

    return {
        "user_info": user_info,
        "total_attempts": progress_stats["total_attempts"] or 0,
        "total_time_minutes": progress_stats["total_time"] or 0,
        "avg_time_per_question": round(avg_q_time["avg_time"] or 0, 1),
        "highest_difficulty": highest_diff["attempt_difficulty"] if highest_diff else "None",
        "topic_mastery": student_mastery,
        "current_topic": topic
    }

# --- Question Manager ---

@app.route("/admin/questions")
@admin_required
def admin_questions():
    db = get_db()
    topics = db.execute("SELECT id, name FROM topics").fetchall()
    
    topic_id = request.args.get("topic_id", type=int)
    difficulty = request.args.get("difficulty", type=int)
    
    questions = []
    count = 0
    if topic_id and difficulty:
        questions = db.execute(
            "SELECT * FROM quiz_questions WHERE topic_id = ? AND difficulty = ?",
            (topic_id, difficulty)
        ).fetchall()
        count = len(questions)
        
    return render_template("admin/questions.html", 
                         topics=topics, 
                         questions=questions, 
                         count=count,
                         selected_topic=topic_id,
                         selected_diff=difficulty)

@app.route("/admin/questions/add", methods=["POST"])
@admin_required
def admin_questions_add():
    topic_id = request.form.get("topic_id", type=int)
    difficulty = request.form.get("difficulty", type=int)
    q_type = request.form.get("question_type")
    question_text = request.form.get("question", "").strip()
    correct = request.form.get("correct_answer", "").strip()
    
    options = [
        request.form.get("option_a", "").strip(),
        request.form.get("option_b", "").strip(),
        request.form.get("option_c", "").strip(),
        request.form.get("option_d", "").strip()
    ]
    
    if not topic_id or not difficulty or not question_text or not correct:
        flash("All fields except options are required.")
        return redirect(f"/admin/questions?topic_id={topic_id}&difficulty={difficulty}")
        
    db = get_db()
    
    # 1. Check for duplicate
    existing = db.execute(
        "SELECT id FROM quiz_questions WHERE topic_id = ? AND difficulty = ? AND LOWER(question) = LOWER(?)",
        (topic_id, difficulty, question_text)
    ).fetchone()
    
    if existing:
        flash("Duplicate question detected in this category.")
        return redirect(f"/admin/questions?topic_id={topic_id}&difficulty={difficulty}")
        
    # 2. Insert
    db.execute(
        """INSERT INTO quiz_questions 
           (topic_id, question, question_type, option_a, option_b, option_c, option_d, correct_answer, difficulty)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (topic_id, question_text, q_type, options[0], options[1], options[2], options[3], correct, difficulty)
    )
    db.commit()
    flash("Question added successfully.")
    return redirect(f"/admin/questions?topic_id={topic_id}&difficulty={difficulty}")

@app.route("/admin/questions/delete/<int:q_id>", methods=["POST"])
@admin_required
def admin_questions_delete(q_id):
    db = get_db()
    
    # 1. Get topic and difficulty of the question
    q = db.execute("SELECT topic_id, difficulty FROM quiz_questions WHERE id = ?", (q_id,)).fetchone()
    if not q:
        flash("Question not found.")
        return redirect("/admin/questions")
        
    # 2. Check current count
    count = db.execute(
        "SELECT COUNT(*) FROM quiz_questions WHERE topic_id = ? AND difficulty = ?",
        (q['topic_id'], q['difficulty'])
    ).fetchone()[0]
    
    if count <= 5:
        flash(f"Critical Integrity Block: Cannot delete. Category pool is at minimum (5).", "error")
        return redirect(f"/admin/questions?topic_id={q['topic_id']}&difficulty={q['difficulty']}")
        
    # 3. Proceed with deletion
    db.execute("DELETE FROM quiz_questions WHERE id = ?", (q_id,))
    db.commit()
    flash("Question deleted successfully.")
    return redirect(f"/admin/questions?topic_id={q['topic_id']}&difficulty={q['difficulty']}")

# --- Content Manager ---

@app.route("/admin/content")
@admin_required
def admin_content():
    db = get_db()
    # Join with topic_content to get existing metadata
    topics = db.execute("""
        SELECT t.id, t.name, tc.explanation_md as content 
        FROM topics t
        LEFT JOIN topic_content tc ON t.id = tc.topic_id
    """).fetchall()
    
    topic_id = request.args.get("topic_id", type=int)
    selected_topic = None
    if topic_id:
        selected_topic = db.execute("""
            SELECT t.id, t.name, tc.explanation_md as content 
            FROM topics t
            LEFT JOIN topic_content tc ON t.id = tc.topic_id
            WHERE t.id = ?
        """, (topic_id,)).fetchone()
        
    return render_template("admin/content.html", topics=topics, selected_topic=selected_topic)

@app.route("/admin/content/save", methods=["POST"])
@admin_required
def admin_content_save():
    topic_id = request.form.get("topic_id", type=int)
    content = request.form.get("content", "").strip()
    
    if not topic_id:
        flash("Topic ID missing.")
        return redirect("/admin/content")
        
    db = get_db()
    # Content is stored in topic_content table, linked by topic_id
    exists = db.execute("SELECT 1 FROM topic_content WHERE topic_id = ?", (topic_id,)).fetchone()
    
    if exists:
        db.execute("UPDATE topic_content SET explanation_md = ? WHERE topic_id = ?", (content, topic_id))
    else:
        # Get topic name to use as default content_title
        topic_row = db.execute("SELECT name FROM topics WHERE id = ?", (topic_id,)).fetchone()
        if not topic_row:
            flash("Topic not found.")
            return redirect("/admin/content")
            
        db.execute("""
            INSERT INTO topic_content (topic_id, content_title, explanation_md) 
            VALUES (?, ?, ?)
        """, (topic_id, topic_row['name'], content))
        
    db.commit()
    flash("Topic content updated successfully.")
    return redirect(f"/admin/content?topic_id={topic_id}")

# --- Integrity Dashboard ---

@app.route("/admin/integrity")
@admin_required
def admin_integrity():
    db = get_db()
    topics = db.execute("SELECT id, name FROM topics").fetchall()
    
    report = []
    REQUIRED = 5
    
    for t in topics:
        tid = t['id']
        counts = {}
        for d in [1, 2, 3]:
            c = db.execute(
                "SELECT COUNT(*) FROM quiz_questions WHERE topic_id = ? AND difficulty = ?",
                (tid, d)
            ).fetchone()[0]
            counts[d] = c
            
        status = "OK" if all(c >= REQUIRED for c in counts.values()) else "Needs Attention"
        report.append({
            "name": t['name'],
            "easy": counts[1],
            "medium": counts[2],
            "hard": counts[3],
            "status": status
        })
        
    return render_template("admin/integrity.html", report=report)







# --- Main Entry Point ---
if __name__ == "__main__":
    init_db()
    app.run(debug=True)

