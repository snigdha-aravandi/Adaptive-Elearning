-- =========================================
-- Database Schema for Adaptive E-Learning System
-- =========================================
-- This schema supports:
-- - Secure user authentication
-- - Topic dependency (competency graph)
-- - Per-user learning progress tracking
-- =========================================


-- -----------------------------
-- 1. Users Table
-- -----------------------------
-- Stores student accounts securely.
-- Passwords are NEVER stored in plain text.
-- password_hash stores a hashed password (Werkzeug).
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'student'
);


-- -----------------------------
-- 2. Topics Table
-- -----------------------------
-- Represents learning topics/modules.
-- prerequisite_id enables a competency graph.
-- A topic can depend on another topic.
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    prerequisite_id INTEGER,
    FOREIGN KEY (prerequisite_id) REFERENCES topics (id)
);


-- -----------------------------
-- 3. Student Progress Table
-- -----------------------------
-- Tracks per-user progress per topic.
-- Composite primary key ensures:
-- one row per (user, topic).
-- mastery is a score between 0.0 and 1.0.
CREATE TABLE IF NOT EXISTS student_progress (
    user_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL,
    mastery REAL DEFAULT 0.0,
    attempts INTEGER DEFAULT 0,
    time_spent INTEGER DEFAULT 0,

    PRIMARY KEY (user_id, topic_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics (id) ON DELETE CASCADE
);


-- -----------------------------
-- 4. Seed Topics (Optional but Recommended)
-- -----------------------------
-- Preload topics so IDs stay consistent.
INSERT OR IGNORE INTO topics (id, name, prerequisite_id) VALUES
(1, 'Variables', NULL),
(2, 'Conditions', 1),
(3, 'Loops', 2),
(4, 'Functions', 3);
-- ==============================
-- 4. Quiz Questions Table
-- Stores MCQ and Code Output questions per topic
-- ==============================

CREATE TABLE IF NOT EXISTS quiz_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    question_type TEXT CHECK(question_type IN ('mcq', 'code')) NOT NULL,

    -- MCQ options (NULL for code questions)
    option_a TEXT,
    option_b TEXT,
    option_c TEXT,
    option_d TEXT,

    -- Correct answer (option text for MCQ, output for code)
    correct_answer TEXT NOT NULL,

    -- Difficulty level (1 = easy, 2 = medium, 3 = hard)
    difficulty INTEGER DEFAULT 1,

    FOREIGN KEY (topic_id) REFERENCES topics (id)
);
-- Sample quiz questions for Variables (topic_id = 1)

INSERT INTO quiz_questions
(topic_id, question, question_type, option_a, option_b, option_c, option_d, correct_answer, difficulty)
VALUES
(1, 'Which is a valid Python variable name?', 'mcq',
 '2value', '_value', 'value-1', 'value one', '_value', 1),

(1, 'What will be the output?\n\nx = 5\nx = x + 3\nprint(x)',
 'code', NULL, NULL, NULL, NULL, '8', 1);
-- Topic Content Table (Redesigned)
CREATE TABLE IF NOT EXISTS topic_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER UNIQUE,
    content_title TEXT NOT NULL,
    explanation_md TEXT NOT NULL,
    code_sample TEXT,
    youtube_url TEXT,
    reference_url TEXT,
    metadata TEXT,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

-- -----------------------------
-- 5. Quiz Attempts Table
-- -----------------------------
-- Tracks individual quiz sessions.
-- difficulty is stored to enable rule-based mastery calculation.
CREATE TABLE IF NOT EXISTS quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    final_score REAL,
    attempt_difficulty TEXT CHECK(attempt_difficulty IN ('easy', 'medium', 'hard')),
    status TEXT DEFAULT 'started',
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics (id) ON DELETE CASCADE
);

-- -----------------------------
-- 6. Question Responses Table
-- -----------------------------
-- Tracks per-question performance within an attempt.
CREATE TABLE IF NOT EXISTS question_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    selected_option TEXT,
    is_correct BOOLEAN,
    time_spent_seconds INTEGER,
    FOREIGN KEY (attempt_id) REFERENCES quiz_attempts (id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES quiz_questions (id) ON DELETE CASCADE
);
