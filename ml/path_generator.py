# Adaptive Path Generator
# This module decides what the student should learn next based on their current mastery.

import sys
import os

# Ensure we can import from the same directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Prerequisite graph (inline replacement for deleted competency_graph module)
competency_graph = {
    "Variables": [],
    "Conditions": ["Variables"],
    "Loops": ["Conditions"],
    "Functions": ["Loops"],
    "Recursion": ["Functions"]
}

def can_unlock(topic, student_scores):
    """Check if student has met prerequisites for a topic"""
    prerequisites = competency_graph.get(topic, [])
    for prereq in prerequisites:
        if student_scores.get(prereq, 0) < 70:  # 70% threshold
            return False
    return True

# Define the standard recommended order of topics
LEARNING_PATH = ["Variables", "Conditions", "Loops", "Functions", "Recursion"]

def recommend_next_step(student_mastery_probs):
    """
    Analyzes the student's mastery probabilities and recommends the next best action.
    
    Args:
        student_mastery_probs (dict): Dictionary mapping topics to mastery probability (0.0 to 1.0).
                                      Example: {"Variables": 0.85, "Conditions": 0.4}
    
    Returns:
        tuple: (Recommended Topic Name, Explanation String)
    """
    
    print("Analyzing student's learning path...")
    
    # We need to cover the mastery probabilities (0.0-1.0) to scores (0-100)
    # because our competency_graph module expects percentage scores.
    student_scores = {topic: prob * 100 for topic, prob in student_mastery_probs.items()}
    
    # Iterate through the curriculum in order
    for topic in LEARNING_PATH:
        
        # Get the current probability (default to 0.0 if not found)
        mastery = student_mastery_probs.get(topic, 0.0)
        
        # Check if the topic is already mastered (Threshold: 0.7 or 70%)
        if mastery >= 0.7:
            continue # Student knows this, move to the next one
            
        # If we reach here, this topic is NOT mastered yet.
        # Now we check if they are ALLOWED to start/continue it.
        if can_unlock(topic, student_scores):
            # Case A: They have tried it before but mastery is low (0 < mastery < 0.7)
            if mastery > 0.0:
                return topic, f"Review '{topic}'. Your mastery is {int(mastery*100)}%, aim for 70%."
            
            # Case B: They haven't started it yet (mastery == 0)
            else:
                return topic, f"Start new topic: '{topic}'."
        else:
            # Case C: They are blocked by a prerequisite.
            # (Note: In a linear sequential check, we usually find the bottleneck earlier,
            # but this handles cases where they might have skipped ahead.)
            prereqs = competency_graph.get(topic, [])
            # Find which specific prerequisite is lacking
            for p in prereqs:
                if student_mastery_probs.get(p, 0.0) < 0.7:
                    return p, f"Go back! You need to master '{p}' before '{topic}'."
    
    # If loop finishes, they mastered everything!
    return "Complete", "Congratulations! You have mastered the entire curriculum."

# --- Main Test Block ---
if __name__ == "__main__":
    # Scenario 1: Just starting
    student_1 = {} 
    topic, reason = recommend_next_step(student_1)
    print(f"Student 1 Recommendation: {topic} ({reason})")
    
    # Scenario 2: Mastered Variables, needs to start Conditions
    student_2 = {"Variables": 0.9}
    topic, reason = recommend_next_step(student_2)
    print(f"Student 2 Recommendation: {topic} ({reason})")

    # Scenario 3: Struggling with Conditions
    student_3 = {"Variables": 0.85, "Conditions": 0.4}
    topic, reason = recommend_next_step(student_3)
    print(f"Student 3 Recommendation: {topic} ({reason})")
    
    # Scenario 4: Mastered up to Loops, hasn't started Functions
    student_4 = {"Variables": 0.95, "Conditions": 0.88, "Loops": 0.75}
    topic, reason = recommend_next_step(student_4)
    print(f"Student 4 Recommendation: {topic} ({reason})")
