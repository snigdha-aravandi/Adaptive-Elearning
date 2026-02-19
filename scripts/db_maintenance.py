import sqlite3
import argparse
import sys
import os

# Ensure we can import from parent directory if needed, though mostly standalone
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', 'instance', 'database.db')
# Fallback if instance folder logic differs in dev
if not os.path.exists(DB_PATH):
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'database.db')

def get_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Error connecting to DB at {DB_PATH}: {e}")
        sys.exit(1)

def check_distribution():
    print(f"Checking Question Bank Distribution ({DB_PATH})...")
    conn = get_db()
    
    query = """
    SELECT t.name as topic, q.difficulty, count(*) as count
    FROM quiz_questions q
    JOIN topics t ON q.topic_id = t.id
    GROUP BY t.name, q.difficulty
    ORDER BY t.name, q.difficulty
    """
    
    rows = conn.execute(query).fetchall()
    
    print(f"{'TOPIC':<20} | {'DIFFICULTY':<10} | {'COUNT':<5} | {'REQ':<5} | {'MISSING':<8}")
    print("-" * 65)
    
    if not rows:
        print("No questions found.")
        return

    REQUIRED = 5
    for row in rows:
        diff_map = {1: 'Easy', 2: 'Medium', 3: 'Hard'}
        diff = diff_map.get(row['difficulty'], str(row['difficulty']))
        count = row['count']
        missing = max(0, REQUIRED - count)
        
        miss_str = f"!! {missing} !!" if missing > 0 else "OK"
        print(f"{row['topic']:<20} | {diff:<10} | {count:<5} | {REQUIRED:<5} | {miss_str:<8}")
    
    conn.close()

def clean_duplicates():
    print("Scanning for duplicate questions...")
    conn = get_db()
    
    # Identify duplicates: Same topic, difficulty, and question text
    query = """
    SELECT topic_id, difficulty, question, COUNT(*) as cnt, MIN(id) as keep_id
    FROM quiz_questions
    GROUP BY topic_id, difficulty, question
    HAVING cnt > 1
    """
    
    duplicates = conn.execute(query).fetchall()
    
    if not duplicates:
        print("No duplicates found. Database is clean.")
        conn.close()
        return

    print(f"Found {len(duplicates)} sets of duplicates. Cleaning...")
    
    deleted_count = 0
    for dup in duplicates:
        # Delete all except the one to keep
        del_query = """
        DELETE FROM quiz_questions 
        WHERE topic_id = ? AND difficulty = ? AND question = ? AND id != ?
        """
        cursor = conn.execute(del_query, (dup['topic_id'], dup['difficulty'], dup['question'], dup['keep_id']))
        deleted_count += cursor.rowcount
    
    conn.commit()
    conn.close()
    print(f"Removed {deleted_count} duplicate entries.")

def enforce_policy():
    print("Enforcing Core Integrity Policy (Min 5 Questions per Difficulty)...")
    conn = get_db()
    
    query = """
    SELECT t.name as topic, q.difficulty, count(*) as count
    FROM quiz_questions q
    JOIN topics t ON q.topic_id = t.id
    GROUP BY t.name, q.difficulty
    """
    
    rows = conn.execute(query).fetchall()
    conn.close()
    
    # Organize by topic
    stats = {}
    for row in rows:
        stats[(row['topic'], row['difficulty'])] = row['count']
        
    # We need to know ALL topics to check for missing entries (0 count)
    conn = get_db()
    topics = conn.execute("SELECT name FROM topics").fetchall()
    conn.close()
    
    violations = 0
    REQUIRED = 5
    
    print(f"{'TOPIC':<20} | {'DIFFICULTY':<10} | {'STATUS':<10} | {'DETAILS'}")
    print("-" * 60)
    
    for topic_row in topics:
        topic = topic_row['name']
        for diff_code, diff_name in [(1, 'Easy'), (2, 'Medium'), (3, 'Hard')]:
            count = stats.get((topic, diff_code), 0)
            
            if count < REQUIRED:
                print(f"{topic:<20} | {diff_name:<10} | {'FAIL':<10} | Found {count}, Need {REQUIRED}")
                violations += 1
            else:
                print(f"{topic:<20} | {diff_name:<10} | {'PASS':<10} | {count} OK")

    if violations > 0:
        print(f"\n[ERROR] Integrity Check Failed! {violations} violations found.")
        sys.exit(1)
    else:
        print("\n[SUCCESS] Question Bank Integrity Verified.")
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="Adaptive E-Learning DB Maintenance")
    parser.add_argument('--check', action='store_true', help='Check question distribution')
    parser.add_argument('--clean', action='store_true', help='Remove duplicate questions')
    parser.add_argument('--enforce', action='store_true', help='Enforce minimum question policy')
    
    args = parser.parse_args()
    
    if args.check:
        check_distribution()
    elif args.clean:
        clean_duplicates()
    elif args.enforce:
        enforce_policy()
    else:
        print("Please specify an action: --check, --clean, or --enforce")
        check_distribution()

if __name__ == "__main__":
    main()
