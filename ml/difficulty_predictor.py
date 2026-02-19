"""
ML-Based Difficulty Predictor
Uses Logistic Regression to recommend quiz difficulty based on student history.

Academic Justification:
- Replaces hardcoded difficulty thresholds with data-driven predictions
- Learns from actual student performance patterns
- Simple, explainable model suitable for academic defense
"""

import sqlite3
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import pickle
import os

MODEL_PATH = "ml/models/difficulty_model.pkl"
SCALER_PATH = "ml/models/scaler.pkl"

class DifficultyPredictor:
    def __init__(self):
        self.model = None
        self.scaler = None
        self.load_model()
    
    def load_model(self):
        """Load pre-trained model or create new one"""
        if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
            with open(MODEL_PATH, 'rb') as f:
                self.model = pickle.load(f)
            with open(SCALER_PATH, 'rb') as f:
                self.scaler = pickle.load(f)
        else:
            self.model = LogisticRegression(max_iter=1000, random_state=42)
            self.scaler = StandardScaler()
    
    def extract_features(self, user_id, topic_id, db_path="database/database.db"):
        """
        Extract features from student's quiz history.
        
        Features:
        1. Current mastery for this topic (0.0-1.0)
        2. Average score on last 3 attempts (0-100)
        3. Total attempts on this topic
        4. Success rate (% of quizzes passed with >70%)
        5. Average mastery across all topics
        """
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Feature 1: Current mastery
        mastery_row = conn.execute(
            "SELECT mastery FROM student_progress WHERE user_id=? AND topic_id=?",
            (user_id, topic_id)
        ).fetchone()
        current_mastery = mastery_row["mastery"] if mastery_row else 0.0
        
        # Feature 2 & 3: Recent performance
        recent_attempts = conn.execute(
            """SELECT final_score FROM quiz_attempts 
               WHERE user_id=? AND topic_id=? AND status='completed'
               ORDER BY end_time DESC LIMIT 3""",
            (user_id, topic_id)
        ).fetchall()
        
        avg_recent_score = np.mean([a["final_score"] for a in recent_attempts]) if recent_attempts else 0

        
        # Feature 4: Success rate
        all_attempts = conn.execute(
            """SELECT final_score FROM quiz_attempts 
               WHERE user_id=? AND topic_id=? AND status='completed'""",
            (user_id, topic_id)
        ).fetchall()
        
        total_attempts = len(all_attempts)
        
        success_rate = 0
        if all_attempts:
            passed = sum(1 for a in all_attempts if a["final_score"] >= 70)
            success_rate = (passed / len(all_attempts)) * 100
        
        # Feature 5: Overall mastery
        all_mastery = conn.execute(
            "SELECT AVG(mastery) as avg_mastery FROM student_progress WHERE user_id=?",
            (user_id,)
        ).fetchone()
        overall_mastery = all_mastery["avg_mastery"] if all_mastery["avg_mastery"] else 0.0
        
        conn.close()
        
        return np.array([
            current_mastery,
            avg_recent_score,
            total_attempts,
            success_rate,
            overall_mastery
        ]).reshape(1, -1)
    
    def predict_difficulty(self, user_id, topic_id):
        """
        Predict optimal difficulty level based on Binary Readiness.
        
        Readiness Levels:
        0 (Not Ready) -> 'easy'
        1 (Ready) -> 'medium' (or 'hard' if mastery is high)
        """
        features = self.extract_features(user_id, topic_id)
        
        # Rule-based fallback for new students (< 2 attempts)
        if features[0][2] < 2:
            return 'easy'
        
        # ML prediction
        if self.model:
            features_scaled = self.scaler.transform(features)
            readiness_prediction = self.model.predict(features_scaled)[0]
            
            # Map Binary Readiness to Difficulty
            if readiness_prediction == 0:
                return 'easy'
            else:
                # If Ready, check mastery to decide between Medium/Hard
                current_mastery = features[0][0]
                if current_mastery >= 0.7:
                    return 'hard'
                else:
                    return 'medium'
        else:
            # Fallback if model missing
            mastery = features[0][0]
            if mastery >= 0.7: return 'hard'
            elif mastery >= 0.4: return 'medium'
            else: return 'easy'
    
    def train(self, db_path="database/database.db"):
        """
        Train Random Forest model or Binary Readiness.
        
        Target Labels (y):
        0 (Not Ready): Avg Score < 65 OR Success Rate < 60%
        1 (Ready): Avg Score >= 65 AND Success Rate >= 60%
        """
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        from sklearn.ensemble import RandomForestClassifier
        
        user_topics = conn.execute(
            """SELECT DISTINCT user_id, topic_id FROM quiz_attempts 
               WHERE status='completed'"""
        ).fetchall()
        
        X = []
        y = []
        
        for row in user_topics:
            u_id, t_id = row["user_id"], row["topic_id"]
            
            # Get performance stats
            attempts = conn.execute(
                 """SELECT final_score FROM quiz_attempts 
                    WHERE user_id=? AND topic_id=? AND status='completed'
                    ORDER BY end_time DESC LIMIT 3""", 
                 (u_id, t_id)
            ).fetchall()
            
            if not attempts: continue
            
            avg_score = np.mean([a["final_score"] for a in attempts])
            
            # Calculate Success Rate from DB (approximate for label generation)
            all_attempts_rows = conn.execute(
                """SELECT final_score FROM quiz_attempts 
                   WHERE user_id=? AND topic_id=? AND status='completed'""",
                (u_id, t_id)
            ).fetchall()
            
            success_rate = 0
            if all_attempts_rows:
                passed = sum(1 for a in all_attempts_rows if a["final_score"] >= 70)
                success_rate = (passed / len(all_attempts_rows)) * 100
            
            # GENERATE BINARY GROUND TRUTH LABEL
            # Ready (1) if Avg Score >= 65 AND Success Rate >= 60%
            if avg_score >= 65 and success_rate >= 60:
                label = 1
            else:
                label = 0
                
            features = self.extract_features(u_id, t_id, db_path)
            X.append(features.flatten())
            y.append(label)
        
        conn.close()
        
        if len(X) < 5:
            print("Insufficient data for training (Need 5+ samples).")
            return False
        
        X = np.array(X)
        y = np.array(y)
        
        # Train Random Forest Classifier
        self.model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        self.scaler = StandardScaler()
        
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        
        # Save model
        os.makedirs("ml/models", exist_ok=True)
        with open(MODEL_PATH, 'wb') as f:
            pickle.dump(self.model, f)
        with open(SCALER_PATH, 'wb') as f:
            pickle.dump(self.scaler, f)
        
        acc = self.model.score(X_scaled, y)
        print(f"Model trained on {len(X)} samples.")
        print(f"Binary Classification Accuracy (Ready/Not Ready): {acc*100:.2f}%")
        
        # Feature Importance
        importances = self.model.feature_importances_
        feature_names = ["Mastery", "AvgScore", "Attempts", "SuccessRate", "OverallMastery"]
        print("\nFeature Importances:")
        for name, imp in sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True):
            print(f"  {name}: {imp:.4f}")
            
        return True

# Global instance
predictor = DifficultyPredictor()
