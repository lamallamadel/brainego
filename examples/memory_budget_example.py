#!/usr/bin/env python3
"""
Example demonstrating MemoryBudgetAllocator usage with query complexity estimation,
dynamic token allocation, Mem0 scoring, and promotion/demotion mechanism.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from memory_budget_allocator import (
    MemoryBudgetAllocator,
    MemoryItem,
    MemoryTier,
    WorkspaceConfig,
    QueryComplexity
)


def create_sample_memories():
    """Create sample memory items for demonstration."""
    now = datetime.now(timezone.utc)
    
    memories = [
        # Working memory (recent, high-priority)
        MemoryItem(
            memory_id="m1",
            text="User is currently working on implementing a REST API with FastAPI",
            tier=MemoryTier.WORKING,
            timestamp=now - timedelta(hours=1),
            user_id="alice",
            relevance_score=0.9,
            importance_score=0.8,
            metadata={"category": "current_task"}
        ),
        MemoryItem(
            memory_id="m2",
            text="The API needs to handle authentication using JWT tokens",
            tier=MemoryTier.WORKING,
            timestamp=now - timedelta(hours=2),
            user_id="alice",
            relevance_score=0.85,
            importance_score=0.7,
            metadata={"category": "current_task"}
        ),
        MemoryItem(
            memory_id="m3",
            text="User mentioned performance is critical, need to optimize database queries",
            tier=MemoryTier.WORKING,
            timestamp=now - timedelta(minutes=30),
            user_id="alice",
            relevance_score=0.95,
            importance_score=0.9,
            metadata={"category": "requirements"}
        ),
        
        # Project memory (session context)
        MemoryItem(
            memory_id="m4",
            text="Project uses PostgreSQL as primary database with connection pooling",
            tier=MemoryTier.PROJECT,
            timestamp=now - timedelta(days=1),
            user_id="alice",
            relevance_score=0.7,
            importance_score=0.8,
            metadata={"category": "architecture"}
        ),
        MemoryItem(
            memory_id="m5",
            text="Tech stack includes FastAPI, SQLAlchemy, Pydantic, and Redis for caching",
            tier=MemoryTier.PROJECT,
            timestamp=now - timedelta(days=2),
            user_id="alice",
            relevance_score=0.65,
            importance_score=0.7,
            metadata={"category": "architecture"}
        ),
        MemoryItem(
            memory_id="m6",
            text="API follows OpenAPI 3.0 specification for documentation",
            tier=MemoryTier.PROJECT,
            timestamp=now - timedelta(days=1, hours=12),
            user_id="alice",
            relevance_score=0.6,
            importance_score=0.6,
            metadata={"category": "standards"}
        ),
        
        # Long-term memory (historical facts)
        MemoryItem(
            memory_id="m7",
            text="User prefers Python for backend development and has 5 years experience",
            tier=MemoryTier.LONG_TERM,
            timestamp=now - timedelta(days=30),
            user_id="alice",
            relevance_score=0.5,
            importance_score=0.9,
            metadata={"category": "preferences"}
        ),
        MemoryItem(
            memory_id="m8",
            text="User typically works in Pacific timezone (UTC-8)",
            tier=MemoryTier.LONG_TERM,
            timestamp=now - timedelta(days=60),
            user_id="alice",
            relevance_score=0.3,
            importance_score=0.5,
            metadata={"category": "profile"}
        ),
        
        # RAG memory (retrieved documents)
        MemoryItem(
            memory_id="m9",
            text="FastAPI documentation: FastAPI is a modern web framework for building APIs with Python 3.7+",
            tier=MemoryTier.RAG,
            timestamp=now - timedelta(hours=3),
            user_id="alice",
            relevance_score=0.8,
            importance_score=0.7,
            metadata={"source": "fastapi_docs"}
        ),
        MemoryItem(
            memory_id="m10",
            text="JWT authentication best practices: Always use HTTPS, set appropriate expiration times",
            tier=MemoryTier.RAG,
            timestamp=now - timedelta(hours=2),
            user_id="alice",
            relevance_score=0.85,
            importance_score=0.8,
            metadata={"source": "security_guide"}
        ),
    ]
    
    return memories


def demonstrate_basic_allocation():
    """Demonstrate basic memory budget allocation."""
    print("=" * 80)
    print("BASIC MEMORY BUDGET ALLOCATION")
    print("=" * 80)
    
    # Initialize allocator
    allocator = MemoryBudgetAllocator(log_allocations=True)
    
    # Create sample memories
    memories = create_sample_memories()
    
    # Test queries with different complexity levels
    queries = [
        "What am I working on?",  # Simple
        "How should I implement JWT authentication in my FastAPI project?",  # Medium
        "Explain the optimal architecture for implementing a high-performance REST API with FastAPI, including database optimization strategies and caching mechanisms",  # Expert
    ]
    
    for query in queries:
        print(f"\nQuery: {query}")
        print("-" * 80)
        
        result = allocator.allocate_memory_budget(
            query=query,
            available_memories=memories.copy(),
            workspace_id="default"
        )
        
        print(f"Complexity: {result['complexity']}")
        print(f"Total tokens allocated: {result['total_tokens_allocated']}")
        print(f"Total memories selected: {result['total_memories_selected']}")
        print(f"Processing time: {result['processing_time_ms']}ms")
        
        print("\nTier breakdown:")
        for tier_name, tier_data in result["tiers"].items():
            print(f"  {tier_name.upper()}:")
            print(f"    Budget: {tier_data['budget_tokens']} tokens")
            print(f"    Used: {tier_data['tokens_used']} tokens ({tier_data['utilization_pct']}%)")
            print(f"    Memories: {tier_data['memories_selected']}/{tier_data['memories_available']}")
            
            if tier_data['memories_selected'] > 0:
                print(f"    Top memory: {tier_data['selected_memories'][0]['text_preview']}")
        
        print()


def demonstrate_workspace_configs():
    """Demonstrate workspace-specific configurations."""
    print("=" * 80)
    print("WORKSPACE-SPECIFIC CONFIGURATIONS")
    print("=" * 80)
    
    # Create custom workspace configurations
    allocator = MemoryBudgetAllocator()
    
    # Development workspace - focus on working memory
    dev_config = WorkspaceConfig(
        workspace_id="development",
        max_total_tokens=4096,
        working_memory_pct=0.50,  # 50% for immediate context
        project_memory_pct=0.30,  # 30% for project
        long_term_memory_pct=0.10,  # 10% for history
        rag_memory_pct=0.10,  # 10% for docs
    )
    allocator.register_workspace(dev_config)
    
    # Research workspace - focus on RAG and long-term
    research_config = WorkspaceConfig(
        workspace_id="research",
        max_total_tokens=16384,
        working_memory_pct=0.15,
        project_memory_pct=0.20,
        long_term_memory_pct=0.25,
        rag_memory_pct=0.40,  # 40% for retrieved documents
        complexity_multipliers={
            QueryComplexity.SIMPLE: 0.5,
            QueryComplexity.MEDIUM: 1.2,
            QueryComplexity.COMPLEX: 1.8,
            QueryComplexity.EXPERT: 2.5
        }
    )
    allocator.register_workspace(research_config)
    
    # Test same query in different workspaces
    query = "How can I optimize database queries for better performance?"
    memories = create_sample_memories()
    
    for workspace_id in ["development", "research"]:
        print(f"\nWorkspace: {workspace_id}")
        print("-" * 80)
        
        result = allocator.allocate_memory_budget(
            query=query,
            available_memories=memories.copy(),
            workspace_id=workspace_id
        )
        
        print(f"Max tokens: {allocator.workspace_configs[workspace_id].max_total_tokens}")
        print(f"Total allocated: {result['total_tokens_allocated']}")
        print(f"Memories selected: {result['total_memories_selected']}")
        
        print("\nTier allocation:")
        for tier_name in ["working", "project", "long_term", "rag"]:
            tier_data = result["tiers"][tier_name]
            print(f"  {tier_name}: {tier_data['tokens_used']}/{tier_data['budget_tokens']} "
                  f"({tier_data['memories_selected']} memories)")
        print()


def demonstrate_promotion_demotion():
    """Demonstrate promotion/demotion mechanism."""
    print("=" * 80)
    print("PROMOTION/DEMOTION MECHANISM")
    print("=" * 80)
    
    config = WorkspaceConfig(workspace_id="default")
    allocator = MemoryBudgetAllocator()
    
    # Create memories with varying access patterns
    now = datetime.now(timezone.utc)
    memories = [
        # High-performing memory (should be promoted)
        MemoryItem(
            memory_id="high_perf",
            text="Frequently accessed important information",
            tier=MemoryTier.PROJECT,
            timestamp=now - timedelta(hours=12),
            relevance_score=0.9,
            importance_score=0.9,
            access_count=5,
            last_accessed=now - timedelta(minutes=10)
        ),
        
        # Low-performing memory (should be demoted)
        MemoryItem(
            memory_id="low_perf",
            text="Rarely used outdated information",
            tier=MemoryTier.WORKING,
            timestamp=now - timedelta(days=7),
            relevance_score=0.3,
            importance_score=0.2,
            access_count=0,
            last_accessed=None
        ),
        
        # Medium-performing memory (no change)
        MemoryItem(
            memory_id="medium_perf",
            text="Moderately relevant information",
            tier=MemoryTier.PROJECT,
            timestamp=now - timedelta(days=2),
            relevance_score=0.6,
            importance_score=0.5,
            access_count=2,
            last_accessed=now - timedelta(days=1)
        ),
    ]
    
    # Score memories first
    for item in memories:
        allocator.calculate_memory_score(item, config)
    
    # Evaluate promotion/demotion
    result = allocator.evaluate_promotion_demotion(memories, config)
    
    print(f"\nTotal evaluated: {result['total_evaluated']}")
    print(f"Promotions: {len(result['promotions'])}")
    print(f"Demotions: {len(result['demotions'])}")
    
    if result['promotions']:
        print("\nPROMOTIONS:")
        for promo in result['promotions']:
            print(f"  Memory {promo['memory_id']}:")
            print(f"    {promo['current_tier']} → {promo['target_tier']}")
            print(f"    Promotion score: {promo['promotion_score']}")
            print(f"    Access count: {promo['access_count']}")
            print(f"    Reason: {promo['reason']}")
    
    if result['demotions']:
        print("\nDEMOTIONS:")
        for demo in result['demotions']:
            print(f"  Memory {demo['memory_id']}:")
            print(f"    {demo['current_tier']} → {demo['target_tier']}")
            print(f"    Promotion score: {demo['promotion_score']}")
            print(f"    Access count: {demo['access_count']}")
            print(f"    Reason: {demo['reason']}")


def demonstrate_statistics():
    """Demonstrate allocation statistics."""
    print("\n" + "=" * 80)
    print("ALLOCATION STATISTICS")
    print("=" * 80)
    
    allocator = MemoryBudgetAllocator(log_allocations=False)
    memories = create_sample_memories()
    
    # Perform several allocations
    queries = [
        "What is my current task?",
        "How do I implement authentication?",
        "Explain the project architecture in detail",
        "What are my coding preferences?",
    ]
    
    for query in queries:
        allocator.allocate_memory_budget(
            query=query,
            available_memories=memories.copy()
        )
    
    # Get statistics
    stats = allocator.get_allocation_statistics()
    
    print(f"\nTotal allocations: {stats['total_allocations']}")
    print(f"\nAverages:")
    print(f"  Tokens allocated: {stats['averages']['tokens_allocated']}")
    print(f"  Memories selected: {stats['averages']['memories_selected']}")
    print(f"  Processing time: {stats['averages']['processing_time_ms']}ms")
    
    print(f"\nComplexity distribution:")
    for complexity, count in stats['complexity_distribution'].items():
        print(f"  {complexity}: {count}")
    
    print(f"\nTier statistics:")
    for tier_name, tier_stats in stats['tier_statistics'].items():
        print(f"  {tier_name}:")
        print(f"    Avg utilization: {tier_stats['avg_utilization_pct']:.2f}%")
        print(f"    Avg memories: {tier_stats['avg_memories_selected']:.2f}")
        print(f"    Avg tokens: {tier_stats['avg_tokens_used']:.2f}")
    
    # Export allocation log
    log_file = "allocation_log.json"
    allocator.export_allocation_log(log_file)
    print(f"\nExported allocation log to: {log_file}")


def demonstrate_query_complexity():
    """Demonstrate query complexity estimation."""
    print("\n" + "=" * 80)
    print("QUERY COMPLEXITY ESTIMATION")
    print("=" * 80)
    
    allocator = MemoryBudgetAllocator(log_allocations=False)
    
    test_cases = [
        {
            "query": "Hello",
            "context": None,
            "expected": "simple"
        },
        {
            "query": "How do I create a REST API?",
            "context": {"history_length": 3},
            "expected": "medium"
        },
        {
            "query": "Explain the differences between synchronous and asynchronous programming in Python, and analyze the impact on API performance",
            "context": {"history_length": 10, "turn_count": 5},
            "expected": "complex"
        },
        {
            "query": "Design and implement a scalable microservices architecture with event-driven communication, explain the optimization strategies for database queries, and evaluate the trade-offs between different caching mechanisms",
            "context": {"history_length": 15, "turn_count": 8, "requires_retrieval": True},
            "expected": "expert"
        },
    ]
    
    print("\nQuery complexity analysis:")
    for i, test_case in enumerate(test_cases, 1):
        complexity = allocator.estimate_query_complexity(
            test_case["query"],
            test_case["context"]
        )
        
        print(f"\n{i}. Query: {test_case['query'][:80]}...")
        print(f"   Context: {test_case['context']}")
        print(f"   Estimated: {complexity.value}")
        print(f"   Expected: {test_case['expected']}")
        print(f"   Match: {'✓' if complexity.value == test_case['expected'] else '✗'}")


def demonstrate_mem0_scoring():
    """Demonstrate Mem0 scoring formula."""
    print("\n" + "=" * 80)
    print("MEM0 SCORING FORMULA (Relevance × Importance × Freshness)")
    print("=" * 80)
    
    config = WorkspaceConfig(
        workspace_id="default",
        relevance_weight=0.5,
        importance_weight=0.3,
        freshness_weight=0.2
    )
    allocator = MemoryBudgetAllocator()
    
    now = datetime.now(timezone.utc)
    
    test_memories = [
        {
            "name": "Recent, highly relevant",
            "item": MemoryItem(
                memory_id="m1",
                text="Recent important information",
                tier=MemoryTier.WORKING,
                timestamp=now - timedelta(hours=1),
                relevance_score=0.9,
                importance_score=0.8
            )
        },
        {
            "name": "Old but important",
            "item": MemoryItem(
                memory_id="m2",
                text="Historical critical fact",
                tier=MemoryTier.LONG_TERM,
                timestamp=now - timedelta(days=30),
                relevance_score=0.7,
                importance_score=0.95
            )
        },
        {
            "name": "Recent but less relevant",
            "item": MemoryItem(
                memory_id="m3",
                text="Recent minor detail",
                tier=MemoryTier.WORKING,
                timestamp=now - timedelta(minutes=30),
                relevance_score=0.5,
                importance_score=0.3
            )
        },
    ]
    
    print(f"\nScoring weights:")
    print(f"  Relevance: {config.relevance_weight}")
    print(f"  Importance: {config.importance_weight}")
    print(f"  Freshness: {config.freshness_weight}")
    print(f"  Half-life: {config.freshness_half_life_hours} hours")
    
    print("\nMemory scores:")
    for test in test_memories:
        item = test["item"]
        score = allocator.calculate_memory_score(item, config, now)
        
        print(f"\n{test['name']}:")
        print(f"  Relevance: {item.relevance_score:.4f}")
        print(f"  Importance: {item.importance_score:.4f}")
        print(f"  Freshness: {item.freshness_score:.4f}")
        print(f"  Combined: {item.combined_score:.4f}")
        print(f"  Age: {(now - item.timestamp).total_seconds() / 3600:.1f} hours")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("MEMORY BUDGET ALLOCATOR - COMPREHENSIVE DEMONSTRATION")
    print("=" * 80 + "\n")
    
    demonstrate_basic_allocation()
    demonstrate_workspace_configs()
    demonstrate_promotion_demotion()
    demonstrate_query_complexity()
    demonstrate_mem0_scoring()
    demonstrate_statistics()
    
    print("\n" + "=" * 80)
    print("DEMONSTRATION COMPLETE")
    print("=" * 80 + "\n")
