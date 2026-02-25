#!/usr/bin/env python3
"""
Example script demonstrating RAG query endpoint with context-augmented responses.

This script shows how to:
1. Perform RAG queries with cosine similarity search
2. Configure top-k retrieval (default k=5)
3. Use metadata filtering
4. Generate augmented responses via MAX Serve
"""

import httpx
import asyncio
import json
from typing import Dict, List, Any, Optional


API_BASE_URL = "http://localhost:8000"


async def rag_query(
    query: str,
    k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.7,
    top_p: float = 0.9,
    max_tokens: int = 2048,
    include_context: bool = True
):
    """
    Query the RAG system for context-augmented responses.
    
    Args:
        query: User query text
        k: Number of top results to retrieve (1-20, default 5)
        filters: Optional metadata filters
        messages: Optional chat history
        temperature: Sampling temperature (0.0-2.0)
        top_p: Nucleus sampling parameter (0.0-1.0)
        max_tokens: Maximum tokens to generate
        include_context: Include retrieved context in response
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {
            "query": query,
            "k": k,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "include_context": include_context
        }
        
        if filters:
            payload["filters"] = filters
        
        if messages:
            payload["messages"] = messages
        
        response = await client.post(
            f"{API_BASE_URL}/v1/rag/query",
            json=payload
        )
        response.raise_for_status()
        return response.json()


async def ingest_sample_data():
    """Ingest sample documents for testing."""
    documents = [
        {
            "text": """
            Machine Learning is a subset of Artificial Intelligence that enables 
            systems to learn and improve from experience without being explicitly 
            programmed. It focuses on developing algorithms that can access data 
            and use it to learn for themselves. The primary goal is to allow 
            computers to learn automatically without human intervention.
            
            There are three main types of machine learning: supervised learning, 
            unsupervised learning, and reinforcement learning. Supervised learning 
            uses labeled data to train models. Unsupervised learning finds patterns 
            in unlabeled data. Reinforcement learning learns through trial and error 
            with rewards and penalties.
            """,
            "metadata": {
                "title": "Introduction to Machine Learning",
                "category": "ai",
                "topic": "machine_learning",
                "difficulty": "beginner"
            }
        },
        {
            "text": """
            Deep Learning is a specialized subset of machine learning that uses 
            neural networks with multiple layers (deep neural networks). These 
            networks can learn hierarchical representations of data, making them 
            particularly effective for complex tasks like image recognition, 
            natural language processing, and speech recognition.
            
            Convolutional Neural Networks (CNNs) excel at image processing tasks. 
            Recurrent Neural Networks (RNNs) and Long Short-Term Memory (LSTM) 
            networks are designed for sequential data like text and time series. 
            Transformers, introduced in 2017, have revolutionized NLP with their 
            attention mechanisms.
            """,
            "metadata": {
                "title": "Deep Learning Architectures",
                "category": "ai",
                "topic": "deep_learning",
                "difficulty": "intermediate"
            }
        },
        {
            "text": """
            Natural Language Processing (NLP) is a branch of AI that helps computers 
            understand, interpret, and manipulate human language. NLP combines 
            computational linguistics with statistical, machine learning, and deep 
            learning models to enable computers to process human language in the 
            form of text or voice data.
            
            Common NLP tasks include sentiment analysis, named entity recognition, 
            machine translation, text summarization, and question answering. Recent 
            advances in transformer models like BERT, GPT, and T5 have dramatically 
            improved NLP capabilities across all these tasks.
            """,
            "metadata": {
                "title": "Natural Language Processing Overview",
                "category": "ai",
                "topic": "nlp",
                "difficulty": "intermediate"
            }
        },
        {
            "text": """
            Computer Vision is a field of AI that trains computers to interpret and 
            understand the visual world. Using digital images from cameras and videos 
            and deep learning models, machines can accurately identify and classify 
            objects, and then react to what they "see."
            
            Applications of computer vision include facial recognition, autonomous 
            vehicles, medical image analysis, and augmented reality. State-of-the-art 
            models like ResNet, YOLO, and Vision Transformers have achieved human-level 
            or better performance on many visual recognition tasks.
            """,
            "metadata": {
                "title": "Computer Vision Fundamentals",
                "category": "ai",
                "topic": "computer_vision",
                "difficulty": "intermediate"
            }
        }
    ]
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/v1/rag/ingest/batch",
            json={"documents": documents}
        )
        response.raise_for_status()
        return response.json()


def print_rag_response(result: Dict[str, Any], show_full_context: bool = False):
    """Pretty print RAG query response."""
    print(f"\n{'='*80}")
    print(f"Query: {result['query']}")
    print(f"{'='*80}")
    
    print(f"\n📝 RESPONSE:")
    print(f"{result['response']}")
    
    stats = result['retrieval_stats']
    print(f"\n📊 RETRIEVAL STATISTICS:")
    print(f"  • Chunks retrieved: {stats['chunks_retrieved']}")
    print(f"  • Retrieval time: {stats['retrieval_time_ms']:.2f}ms")
    print(f"  • Generation time: {stats['generation_time_ms']:.2f}ms")
    print(f"  • Total time: {stats['total_time_ms']:.2f}ms")
    
    if stats.get('top_score'):
        print(f"  • Top similarity score: {stats['top_score']:.4f}")
        print(f"  • Average similarity score: {stats['avg_score']:.4f}")
        print(f"  • Minimum similarity score: {stats['min_score']:.4f}")
    
    if result.get('context'):
        print(f"\n📚 RETRIEVED CONTEXT ({len(result['context'])} chunks):")
        for i, ctx in enumerate(result['context'], 1):
            print(f"\n  Context {i} (Score: {ctx['score']:.4f}):")
            print(f"    Metadata: {json.dumps(ctx.get('metadata', {}), indent=6)}")
            if show_full_context:
                print(f"    Text: {ctx['text']}")
            else:
                print(f"    Text: {ctx['text'][:200]}...")
    
    usage = result['usage']
    print(f"\n💬 TOKEN USAGE:")
    print(f"  • Prompt tokens: {usage['prompt_tokens']}")
    print(f"  • Completion tokens: {usage['completion_tokens']}")
    print(f"  • Total tokens: {usage['total_tokens']}")
    print(f"\n{'='*80}\n")


async def main():
    print("=" * 80)
    print("RAG Query Example - Context-Augmented Responses")
    print("=" * 80)
    
    # Ingest sample data
    print("\n1. Ingesting sample AI/ML documents...")
    ingest_result = await ingest_sample_data()
    print(f"✓ Ingested {ingest_result['documents_processed']} documents")
    print(f"  Total chunks: {ingest_result['total_chunks']}")
    print(f"  Total points: {ingest_result['total_points']}")
    
    # Example 1: Basic RAG query with default k=5
    print("\n2. Basic RAG query (default k=5)...")
    result = await rag_query(
        query="What is machine learning and what are its main types?",
        k=5
    )
    print_rag_response(result)
    
    # Example 2: RAG query with top-k=3
    print("\n3. RAG query with top-k=3...")
    result = await rag_query(
        query="Explain deep learning neural network architectures",
        k=3,
        temperature=0.6
    )
    print_rag_response(result)
    
    # Example 3: RAG query with metadata filtering
    print("\n4. RAG query with metadata filtering (topic='nlp')...")
    result = await rag_query(
        query="What are common NLP tasks?",
        k=5,
        filters={"topic": "nlp"},
        temperature=0.7
    )
    print_rag_response(result)
    
    # Example 4: RAG query with difficulty filter
    print("\n5. RAG query filtering by difficulty level...")
    result = await rag_query(
        query="Give me an introduction suitable for beginners",
        k=3,
        filters={"difficulty": "beginner"},
        temperature=0.5
    )
    print_rag_response(result)
    
    # Example 5: Multi-turn conversation with RAG
    print("\n6. Multi-turn conversation with RAG context...")
    result = await rag_query(
        query="What applications does it have?",
        k=4,
        messages=[
            {"role": "user", "content": "Tell me about computer vision"},
            {"role": "assistant", "content": "Computer vision is a field of AI that enables machines to interpret visual information."}
        ],
        temperature=0.7
    )
    print_rag_response(result)
    
    # Example 6: RAG query without including context in response
    print("\n7. RAG query without context details (include_context=False)...")
    result = await rag_query(
        query="What is the difference between supervised and unsupervised learning?",
        k=3,
        include_context=False,
        temperature=0.6
    )
    print_rag_response(result, show_full_context=True)
    
    # Example 7: RAG query with different top-k values
    print("\n8. Comparing different top-k values...")
    query = "Explain transformer models in NLP"
    
    for k in [1, 3, 5]:
        print(f"\n  Testing with k={k}:")
        result = await rag_query(
            query=query,
            k=k,
            temperature=0.7,
            include_context=False
        )
        stats = result['retrieval_stats']
        print(f"    Chunks retrieved: {stats['chunks_retrieved']}")
        print(f"    Top score: {stats.get('top_score', 'N/A')}")
        print(f"    Avg score: {stats.get('avg_score', 'N/A')}")
        print(f"    Total time: {stats['total_time_ms']:.2f}ms")
    
    print("\n" + "=" * 80)
    print("Example completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
