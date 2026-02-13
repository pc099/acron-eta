"""
Test script to check similarity between two semantically identical queries.
"""

import os
from dotenv import load_dotenv
from src.embeddings.engine import EmbeddingEngine, EmbeddingConfig
from src.embeddings.similarity import SimilarityCalculator
import numpy as np

load_dotenv()

def test_similarity():
    """Test similarity between two semantically identical queries."""
    
    # Check if API key is set
    if not os.getenv("COHERE_API_KEY"):
        print("ERROR: COHERE_API_KEY not set!")
        return
    
    # Initialize embedding engine
    config = EmbeddingConfig(provider="cohere")
    engine = EmbeddingEngine(config)
    similarity_calc = SimilarityCalculator()
    
    query1 = "What is Python?"
    query2 = "Can you explain what Python is?"
    
    print(f"Query 1: '{query1}'")
    print(f"Query 2: '{query2}'")
    print("\nGenerating embeddings...")
    
    # Generate embeddings
    emb1 = engine.embed_text(query1)
    emb2 = engine.embed_text(query2)
    
    # Calculate similarity
    similarity = similarity_calc.cosine_similarity(emb1, emb2)
    
    print(f"\nCosine Similarity: {similarity:.4f}")
    print(f"Similarity Percentage: {similarity * 100:.2f}%")
    
    # Check thresholds
    from src.embeddings.threshold import AdaptiveThresholdTuner, DEFAULT_THRESHOLDS
    
    print("\n" + "="*60)
    print("Threshold Analysis:")
    print("="*60)
    
    tuner = AdaptiveThresholdTuner()
    
    for task_type in ["general", "faq"]:
        print(f"\nTask Type: {task_type}")
        for sensitivity in ["high", "medium", "low"]:
            threshold = tuner.get_threshold(task_type, sensitivity)
            matches = similarity >= threshold
            status = "MATCH" if matches else "NO MATCH"
            print(f"  {sensitivity:6} sensitivity: threshold={threshold:.3f} -> {status}")
    
    print("\n" + "="*60)
    print("Recommendation:")
    print("="*60)
    
    if similarity >= 0.80:
        print(f"✅ Similarity ({similarity:.3f}) is high enough for most thresholds")
        print("   These queries SHOULD match in Tier 2 cache")
    else:
        print(f"⚠️  Similarity ({similarity:.3f}) might be too low")
        print("   Consider:")
        print("   1. Using a more lenient threshold for 'general' task type")
        print("   2. Checking if embeddings are being normalized correctly")
        print("   3. Verifying the embedding model quality")

if __name__ == "__main__":
    test_similarity()
