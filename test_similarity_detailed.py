"""
Detailed test to check why semantically identical queries aren't matching.
"""

import os
from dotenv import load_dotenv
from src.embeddings.engine import EmbeddingEngine, EmbeddingConfig
from src.embeddings.similarity import SimilarityCalculator
from src.embeddings.threshold import AdaptiveThresholdTuner
from src.routing.task_detector import TaskTypeDetector

load_dotenv()

def test_detailed():
    """Test similarity and thresholds in detail."""
    
    if not os.getenv("COHERE_API_KEY"):
        print("ERROR: COHERE_API_KEY not set!")
        return
    
    # Initialize components
    config = EmbeddingConfig(provider="cohere")
    engine = EmbeddingEngine(config)
    similarity_calc = SimilarityCalculator()
    tuner = AdaptiveThresholdTuner()
    detector = TaskTypeDetector()
    
    query1 = "What is Python?"
    query2 = "Can you explain what Python is?"
    
    print("="*60)
    print("SEMANTIC SIMILARITY ANALYSIS")
    print("="*60)
    print(f"\nQuery 1: '{query1}'")
    print(f"Query 2: '{query2}'")
    
    # Detect task types
    detection1 = detector.detect(query1)
    detection2 = detector.detect(query2)
    
    print(f"\nTask Detection:")
    print(f"  Query 1: {detection1.task_type} (confidence: {detection1.confidence:.2f})")
    print(f"  Query 2: {detection2.task_type} (confidence: {detection2.confidence:.2f})")
    
    # Generate embeddings
    print("\nGenerating embeddings...")
    emb1 = engine.embed_text(query1)
    emb2 = engine.embed_text(query2)
    
    # Calculate similarity
    similarity = similarity_calc.cosine_similarity(emb1, emb2)
    
    print(f"\nCosine Similarity: {similarity:.4f} ({similarity*100:.2f}%)")
    
    # Check thresholds
    print("\n" + "="*60)
    print("THRESHOLD ANALYSIS")
    print("="*60)
    
    task_type = detection1.task_type  # Use first query's task type
    
    print(f"\nUsing task type: '{task_type}'")
    print("\nThresholds for different sensitivities:")
    
    for sensitivity in ["high", "medium", "low"]:
        threshold = tuner.get_threshold(task_type, sensitivity)
        matches = similarity >= threshold
        status = "✅ MATCH" if matches else "❌ NO MATCH"
        print(f"  {sensitivity:6} sensitivity: threshold={threshold:.3f} -> {status}")
        if matches:
            print(f"    ✓ Similarity ({similarity:.3f}) >= threshold ({threshold:.3f})")
        else:
            diff = threshold - similarity
            print(f"    ✗ Similarity ({similarity:.3f}) < threshold ({threshold:.3f}) by {diff:.3f}")
    
    print("\n" + "="*60)
    print("RECOMMENDATION")
    print("="*60)
    
    # Current optimizer uses "high" sensitivity
    threshold_high = tuner.get_threshold(task_type, "high")
    
    if similarity >= threshold_high:
        print(f"✅ These queries SHOULD match!")
        print(f"   Similarity ({similarity:.3f}) >= threshold ({threshold_high:.3f})")
    else:
        print(f"⚠️  These queries are NOT matching")
        print(f"   Similarity ({similarity:.3f}) < threshold ({threshold_high:.3f})")
        print(f"\n   Options:")
        print(f"   1. Lower threshold for '{task_type}' task type")
        print(f"   2. Improve task detection (should be 'faq' for 'What is...' queries)")
        print(f"   3. Use better embedding model")

if __name__ == "__main__":
    test_detailed()
