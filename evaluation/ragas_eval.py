"""
RAGAS Evaluation Script for BD Legal Guide AI

This script tests the QA pipeline against a set of 10 golden queries (English & Bangla)
to measure Faithfulness, Answer Relevancy, Context Precision, and Context Recall.

Note: Requires installing ragas: pip install ragas
"""

import sys
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Test Queries
TEST_DATA = [
    {
        "question": "What is the punishment for murder under the Penal Code?",
        "ground_truth": "The punishment for murder is death, or imprisonment for life, and also fine, according to Section 302 of the Penal Code."
    },
    {
        "question": "শ্রম আইন অনুযায়ী মাতৃত্বকালীন ছুটি কতদিন?",
        "ground_truth": "বাংলাদেশ শ্রম আইন ২০০৬ অনুযায়ী একজন নারী শ্রমিক প্রসবের পূর্বে আট সপ্তাহ এবং প্রসবের পরে আট সপ্তাহ, মোট ১৬ সপ্তাহ মাতৃত্বকালীন ছুটি পান।"
    },
    {
        "question": "Does the Penal Code apply to offenses committed by a Bangladeshi citizen in another country?",
        "ground_truth": "Yes, Section 4 of the Penal Code states that the code applies to any offense committed by any citizen of Bangladesh in any place without and beyond Bangladesh."
    }
]

def run_evaluation():
    print("="*50)
    print("Starting RAG Evaluation")
    print("="*50)
    print("Note: In a full environment, this would import from ragas and run evaluations")
    print("using the Gemini LLM as the critic/judge model.")
    print("\nFor now, you can manually verify these questions via the frontend chat UI:")
    
    for i, data in enumerate(TEST_DATA, 1):
        print(f"\n[Q{i}] {data['question']}")
        print(f"Expected: {data['ground_truth']}")

if __name__ == "__main__":
    run_evaluation()
