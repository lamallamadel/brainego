#!/usr/bin/env python3
"""
Test script for Agent Router with multi-model deployment.
Tests intent classification and automatic model selection.
"""

import httpx
import json
import time
from typing import Dict, Any


API_URL = "http://localhost:8000"


def send_chat_request(messages: list, show_routing: bool = True) -> Dict[str, Any]:
    """Send a chat completion request."""
    payload = {
        "model": "auto",
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7
    }
    
    response = httpx.post(
        f"{API_URL}/v1/chat/completions",
        json=payload,
        timeout=60.0
    )
    
    result = response.json()
    
    if show_routing:
        metadata = result.get('x-routing-metadata', {})
        print(f"\n{'='*80}")
        print(f"Intent: {metadata.get('intent')}")
        print(f"Model: {metadata.get('model_name')} ({metadata.get('model_id')})")
        print(f"Confidence: {metadata.get('confidence', 0):.2f}")
        print(f"Fallback Used: {metadata.get('fallback_used')}")
        print(f"Total Time: {metadata.get('total_time_seconds', 0):.3f}s")
        print(f"{'='*80}\n")
    
    return result


def test_code_intent():
    """Test code-related query (should route to Qwen Coder)."""
    print("\n🔧 Testing CODE Intent (should route to Qwen 2.5 Coder 7B)")
    print("-" * 80)
    
    messages = [
        {
            "role": "user",
            "content": "Write a Python function to implement binary search with error handling."
        }
    ]
    
    result = send_chat_request(messages)
    response = result['choices'][0]['message']['content']
    print(f"Response: {response[:200]}...")


def test_reasoning_intent():
    """Test reasoning-related query (should route to DeepSeek R1)."""
    print("\n🧠 Testing REASONING Intent (should route to DeepSeek R1 7B)")
    print("-" * 80)
    
    messages = [
        {
            "role": "user",
            "content": "Analyze the problem: If 5 workers can complete a project in 12 days, how many days will it take 8 workers to complete the same project? Explain your reasoning step by step."
        }
    ]
    
    result = send_chat_request(messages)
    response = result['choices'][0]['message']['content']
    print(f"Response: {response[:200]}...")


def test_general_intent():
    """Test general query (should route to Llama 3.3)."""
    print("\n💬 Testing GENERAL Intent (should route to Llama 3.3 8B)")
    print("-" * 80)
    
    messages = [
        {
            "role": "user",
            "content": "What are some healthy breakfast ideas for busy mornings?"
        }
    ]
    
    result = send_chat_request(messages)
    response = result['choices'][0]['message']['content']
    print(f"Response: {response[:200]}...")


def test_mixed_conversation():
    """Test conversation with mixed intents."""
    print("\n🔄 Testing MIXED Conversation (testing intent switching)")
    print("-" * 80)
    
    # First message: general
    print("\nUser: Tell me about artificial intelligence.")
    messages = [
        {"role": "user", "content": "Tell me about artificial intelligence."}
    ]
    result = send_chat_request(messages, show_routing=True)
    
    # Second message: code
    print("\nUser: Can you show me how to implement a neural network in Python?")
    messages.append({
        "role": "assistant",
        "content": result['choices'][0]['message']['content']
    })
    messages.append({
        "role": "user",
        "content": "Can you show me how to implement a neural network in Python?"
    })
    result = send_chat_request(messages, show_routing=True)
    
    # Third message: reasoning
    print("\nUser: What's the computational complexity of training this network?")
    messages.append({
        "role": "assistant",
        "content": result['choices'][0]['message']['content']
    })
    messages.append({
        "role": "user",
        "content": "What's the computational complexity of training this network?"
    })
    result = send_chat_request(messages, show_routing=True)


def check_health():
    """Check API health status."""
    print("\n🏥 Checking API Health")
    print("-" * 80)
    
    response = httpx.get(f"{API_URL}/health", timeout=10.0)
    health = response.json()
    
    print(f"Status: {health['status']}")
    print("\nModels:")
    for model_id, info in health['models'].items():
        status_emoji = "✅" if info['status'] == 'healthy' else "❌"
        print(f"  {status_emoji} {info['name']}: {info['status']}")


def check_router_info():
    """Check router configuration."""
    print("\n⚙️  Router Configuration")
    print("-" * 80)
    
    response = httpx.get(f"{API_URL}/router/info", timeout=10.0)
    info = response.json()
    
    print("\nRouting Strategy:")
    for intent, model in info['routing_strategy'].items():
        print(f"  {intent}: {model}")
    
    print("\nFallback Chains:")
    for model, chain in info['fallback_chains'].items():
        print(f"  {model}: {' → '.join(chain)}")


def check_prometheus_metrics():
    """Check Prometheus metrics."""
    print("\n📊 Prometheus Metrics Sample")
    print("-" * 80)
    
    try:
        response = httpx.get("http://localhost:8001/metrics", timeout=5.0)
        metrics = response.text
        
        # Show sample metrics
        for line in metrics.split('\n'):
            if 'agent_router' in line and not line.startswith('#'):
                print(f"  {line}")
                
    except Exception as e:
        print(f"  Could not fetch metrics: {e}")


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("🚀 Agent Router Test Suite")
    print("="*80)
    
    try:
        # Check health first
        check_health()
        
        # Check router configuration
        check_router_info()
        
        # Run intent tests
        test_general_intent()
        time.sleep(1)
        
        test_code_intent()
        time.sleep(1)
        
        test_reasoning_intent()
        time.sleep(1)
        
        # Test conversation with mixed intents
        test_mixed_conversation()
        
        # Check Prometheus metrics
        check_prometheus_metrics()
        
        print("\n" + "="*80)
        print("✅ All tests completed!")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
