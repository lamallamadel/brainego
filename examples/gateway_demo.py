#!/usr/bin/env python3
"""
Demonstration of the API Gateway unified chat endpoint.
Shows Memory + RAG + Inference integration.
"""

import requests
import json
import time
from typing import Dict, Any

# Configuration
GATEWAY_URL = "http://localhost:9000"
API_KEY = "sk-test-key-123"

# Set up headers
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_response(response: Dict[str, Any]):
    """Pretty print the response."""
    print(f"Status: {response.get('status_code', 'N/A')}")
    
    if response.get('status_code') == 200:
        data = response.get('data', {})
        
        # Print the assistant's response
        choices = data.get('choices', [])
        if choices:
            message = choices[0].get('message', {})
            content = message.get('content', '')
            print(f"\nAssistant: {content}\n")
        
        # Print usage statistics
        usage = data.get('usage', {})
        if usage:
            print(f"Tokens: {usage.get('total_tokens', 0)} "
                  f"(prompt: {usage.get('prompt_tokens', 0)}, "
                  f"completion: {usage.get('completion_tokens', 0)})")
        
        # Print metadata
        metadata = data.get('metadata', {})
        if metadata:
            total_latency = metadata.get('total_latency_ms', 0)
            print(f"Latency: {total_latency:.2f}ms", end="")
            if total_latency < 3000:
                print(" ✓ (under 3s target)")
            else:
                print(" ⚠ (exceeds 3s target)")
            
            # Print component latencies
            if metadata.get('memory_retrieval_ms'):
                print(f"  - Memory: {metadata['memory_retrieval_ms']:.2f}ms "
                      f"({metadata.get('memories_retrieved', 0)} retrieved)")
            if metadata.get('rag_retrieval_ms'):
                print(f"  - RAG: {metadata['rag_retrieval_ms']:.2f}ms "
                      f"({metadata.get('rag_documents_retrieved', 0)} retrieved)")
            if metadata.get('generation_ms'):
                print(f"  - Generation: {metadata['generation_ms']:.2f}ms")
        
        # Print context information
        context = data.get('context', {})
        if context:
            memories = context.get('memories', [])
            if memories:
                print(f"\nRetrieved Memories ({len(memories)}):")
                for i, mem in enumerate(memories[:3], 1):
                    text = mem.get('text', '')[:100]
                    score = mem.get('score', 0)
                    print(f"  {i}. [{score:.2f}] {text}...")
            
            rag_docs = context.get('rag_documents', [])
            if rag_docs:
                print(f"\nRetrieved RAG Documents ({len(rag_docs)}):")
                for i, doc in enumerate(rag_docs[:3], 1):
                    text = doc.get('text', '')[:100]
                    score = doc.get('score', 0)
                    print(f"  {i}. [{score:.2f}] {text}...")
    else:
        print(f"Error: {response.get('error', 'Unknown error')}")


def make_request(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Make a request to the gateway."""
    url = f"{GATEWAY_URL}{endpoint}"
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        return {
            'status_code': response.status_code,
            'data': response.json() if response.status_code == 200 else {},
            'error': response.text if response.status_code != 200 else None
        }
    except requests.exceptions.ConnectionError:
        return {
            'status_code': 0,
            'error': 'Connection failed. Is the gateway running?'
        }
    except Exception as e:
        return {
            'status_code': 0,
            'error': str(e)
        }


def demo_basic_chat():
    """Demo 1: Basic chat without memory or RAG."""
    print_section("Demo 1: Basic Chat (No Memory/RAG)")
    
    payload = {
        "messages": [
            {"role": "user", "content": "What is 2+2? Answer in one sentence."}
        ],
        "max_tokens": 50,
        "use_memory": False,
        "use_rag": False,
        "store_memory": False
    }
    
    print("Request: Basic math question")
    response = make_request("/v1/chat", payload)
    print_response(response)


def demo_memory_storage():
    """Demo 2: Store information in memory."""
    print_section("Demo 2: Memory Storage")
    
    user_id = f"demo-user-{int(time.time())}"
    
    # First message: Store personal information
    payload1 = {
        "messages": [
            {"role": "user", "content": "My name is Alex, I'm a software engineer, "
                                       "and I love Python programming."}
        ],
        "user_id": user_id,
        "max_tokens": 100,
        "use_memory": False,
        "use_rag": False,
        "store_memory": True
    }
    
    print(f"Request: Storing personal information (user_id: {user_id})")
    response1 = make_request("/v1/chat", payload1)
    print_response(response1)
    
    # Wait a moment for memory to be indexed
    print("\nWaiting 2 seconds for memory to be indexed...")
    time.sleep(2)
    
    # Second message: Store preferences
    payload2 = {
        "messages": [
            {"role": "user", "content": "I'm currently learning machine learning "
                                       "and working on a project about NLP."}
        ],
        "user_id": user_id,
        "max_tokens": 100,
        "use_memory": False,
        "use_rag": False,
        "store_memory": True
    }
    
    print("\nRequest: Storing project information")
    response2 = make_request("/v1/chat", payload2)
    print_response(response2)
    
    return user_id


def demo_memory_retrieval(user_id: str):
    """Demo 3: Retrieve and use stored memories."""
    print_section("Demo 3: Memory Retrieval")
    
    payload = {
        "messages": [
            {"role": "user", "content": "Based on what you know about me, "
                                       "what technologies should I focus on?"}
        ],
        "user_id": user_id,
        "max_tokens": 150,
        "use_memory": True,
        "use_rag": False,
        "store_memory": True,
        "memory_limit": 5
    }
    
    print(f"Request: Query with memory retrieval (user_id: {user_id})")
    response = make_request("/v1/chat", payload)
    print_response(response)


def demo_rag_integration():
    """Demo 4: RAG integration (if documents are available)."""
    print_section("Demo 4: RAG Integration")
    
    payload = {
        "messages": [
            {"role": "user", "content": "Tell me about the documentation and features available."}
        ],
        "max_tokens": 150,
        "use_memory": False,
        "use_rag": True,
        "store_memory": False,
        "rag_k": 3
    }
    
    print("Request: Query with RAG context retrieval")
    response = make_request("/v1/chat", payload)
    print_response(response)


def demo_full_integration(user_id: str):
    """Demo 5: Full integration with Memory + RAG + Inference."""
    print_section("Demo 5: Full Integration (Memory + RAG + Inference)")
    
    payload = {
        "messages": [
            {"role": "user", "content": "What do you know about me and what resources "
                                       "are available to help with my learning?"}
        ],
        "user_id": user_id,
        "max_tokens": 200,
        "use_memory": True,
        "use_rag": True,
        "store_memory": True,
        "rag_k": 3,
        "memory_limit": 5,
        "temperature": 0.7
    }
    
    print(f"Request: Full integration query (user_id: {user_id})")
    response = make_request("/v1/chat", payload)
    print_response(response)


def demo_multi_turn_conversation(user_id: str):
    """Demo 6: Multi-turn conversation with context."""
    print_section("Demo 6: Multi-turn Conversation")
    
    conversations = [
        "What are the key concepts in machine learning?",
        "Which of these should I learn first as a beginner?",
        "Can you create a learning plan for me based on what you know about my background?"
    ]
    
    for i, user_message in enumerate(conversations, 1):
        print(f"\n--- Turn {i} ---")
        print(f"User: {user_message}")
        
        payload = {
            "messages": [
                {"role": "user", "content": user_message}
            ],
            "user_id": user_id,
            "max_tokens": 150,
            "use_memory": True,
            "use_rag": True,
            "store_memory": True,
            "memory_limit": 5
        }
        
        response = make_request("/v1/chat", payload)
        print_response(response)
        
        # Small delay between turns
        if i < len(conversations):
            time.sleep(1)


def check_health():
    """Check gateway health."""
    print_section("Gateway Health Check")
    
    try:
        response = requests.get(f"{GATEWAY_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            print(f"Services:")
            for service, status in data.get('services', {}).items():
                emoji = "✓" if status == "healthy" else "✗"
                print(f"  {emoji} {service}: {status}")
            return True
        else:
            print(f"Health check failed: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to gateway. Is it running?")
        print(f"   Expected URL: {GATEWAY_URL}")
        print("\nStart the gateway with:")
        print("  docker compose up -d gateway")
        print("  # or")
        print("  python gateway_service.py")
        return False


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("  API Gateway Demo - Unified Chat Endpoint")
    print("=" * 70)
    print(f"\nGateway URL: {GATEWAY_URL}")
    print(f"API Key: {API_KEY}")
    
    # Check health first
    if not check_health():
        return 1
    
    try:
        # Run demos
        demo_basic_chat()
        
        user_id = demo_memory_storage()
        
        demo_memory_retrieval(user_id)
        
        demo_rag_integration()
        
        demo_full_integration(user_id)
        
        demo_multi_turn_conversation(user_id)
        
        print_section("Demo Complete!")
        print("All demonstrations completed successfully.")
        print(f"\nYour user_id for this session: {user_id}")
        print("You can continue the conversation using this user_id.")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
        return 130
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
