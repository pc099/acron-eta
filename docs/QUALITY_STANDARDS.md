## MANDATORY Requirements

### 1. Type Hints (Every function must have them)
✅ CORRECT:
def embed_text(text: str) -> np.ndarray:
    return embedder.embed(text)

❌ WRONG:
def embed_text(text):
    return embedder.embed(text)

### 2. Docstrings (Every function and class)
✅ CORRECT:
def calculate_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        vec1: First vector
        vec2: Second vector
    
    Returns:
        Similarity (0-1, where 1=identical)
    
    Raises:
        ValueError: If vectors have different lengths
    """
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must match")
    return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))

### 3. Error Handling (All API calls)
✅ CORRECT:
try:
    response = cohere_client.embed(texts=texts)
    return response.embeddings
except ConnectionError as e:
    logger.error(f"Cohere API failed: {e}")
    raise

❌ WRONG:
response = cohere_client.embed(texts=texts)  # No error handling!
return response.embeddings

### 4. Testing (100% coverage required)
✅ CORRECT:
pytest tests/phase2/test_embedding_engine.py -v --cov=src/phase2 --cov-report=html

### 5. Code Style
- Use Black formatter
- Max line length: 100 characters
- No magic numbers (use constants)

### 6. Logging (Every important operation)
✅ CORRECT:
logger.info(f"Processing request: {request_id}")
logger.error(f"Failed: {error}", exc_info=True)

### 7. Configuration (No hardcoded values!)
✅ CORRECT:
SIMILARITY_THRESHOLD = 0.85  # In config.yaml

❌ WRONG:
if similarity >= 0.85:  # Hardcoded!

### 8. Git Commits (Meaningful messages)
✅ CORRECT:
git commit -m "Feat: implement EmbeddingEngine

- Add embed_text and embed_texts methods
- 12 unit tests with 100% coverage
- Error handling for API failures
- Config-driven thresholds"

---

## Red Flags (Code to REJECT)

❌ No type hints
❌ No docstrings
❌ No error handling
❌ Hardcoded values
❌ No tests
❌ No logging
❌ Generic variable names (x, y, data, result)
❌ Functions >50 lines without breaking into smaller functions

If you see these, ask Claude Code to regenerate.
