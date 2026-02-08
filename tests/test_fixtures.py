"""
Sample test data and fixtures for Asahi tests.
"""

SAMPLE_PROMPTS = {
    "short": "What is the capital of France?",
    "medium": (
        "Explain the difference between supervised and unsupervised machine learning. "
        "Include examples of when you would use each approach and mention common "
        "algorithms for both categories."
    ),
    "long": (
        "You are a senior software architect reviewing a microservices architecture "
        "for an e-commerce platform. The system currently has the following services: "
        "user-service, product-service, order-service, payment-service, and "
        "notification-service. Each service has its own database. The team is "
        "experiencing issues with data consistency across services, especially "
        "during the checkout flow where the order-service needs to verify inventory "
        "in product-service and process payment through payment-service atomically. "
        "Please analyze the architecture and propose a solution using the Saga "
        "pattern or event sourcing. Include specific implementation recommendations "
        "for handling failure scenarios and compensating transactions."
    ),
    "empty": "",
    "whitespace": "   ",
}

SAMPLE_QUERIES = [
    {"id": "test_001", "text": "Summarize: AI is transforming healthcare.", "type": "summarization", "expected_output_length": "short"},
    {"id": "test_002", "text": "Classify this sentiment: I love this product!", "type": "classification", "expected_output_length": "short"},
    {"id": "test_003", "text": "What causes the northern lights?", "type": "qa", "expected_output_length": "medium"},
    {"id": "test_004", "text": "If all roses are flowers and some flowers fade quickly, can we conclude that some roses fade quickly?", "type": "reasoning", "expected_output_length": "medium"},
    {"id": "test_005", "text": "Write a haiku about programming.", "type": "creative", "expected_output_length": "short"},
]
