"""
Train the difficulty prediction model.
Run this script after collecting sufficient quiz data.

Usage:
    python ml/train_model.py
"""

from difficulty_predictor import predictor

if __name__ == "__main__":
    print("Training difficulty prediction model...")
    success = predictor.train()
    
    if success:
        print("✓ Model trained and saved successfully!")
        print("  - Model saved to: ml/models/difficulty_model.pkl")
        print("  - Scaler saved to: ml/models/scaler.pkl")
    else:
        print("✗ Training failed. Collect more quiz data.")
        print("  - Minimum required: 10 successful quiz attempts")
