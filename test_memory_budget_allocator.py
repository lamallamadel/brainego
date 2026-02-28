#!/usr/bin/env python3
"""
Basic tests for MemoryBudgetAllocator implementation.
"""

from datetime import datetime, timezone, timedelta
from memory_budget_allocator import (
    MemoryBudgetAllocator,
    MemoryItem,
    MemoryTier,
    WorkspaceConfig,
    QueryComplexity
)


def test_imports():
    """Test that all imports work correctly."""
    print("✓ All imports successful")
    return True


def test_memory_item_creation():
    """Test creating a MemoryItem."""
    item = MemoryItem(
        memory_id="test1",
        text="Test memory content",
        tier=MemoryTier.WORKING,
        timestamp=datetime.now(timezone.utc),
        relevance_score=0.9,
        importance_score=0.8
    )
    assert item.memory_id == "test1"
    assert item.tier == MemoryTier.WORKING
    print("✓ MemoryItem creation works")
    return True


def test_workspace_config():
    """Test WorkspaceConfig creation."""
    config = WorkspaceConfig(
        workspace_id="test_workspace",
        max_total_tokens=4096
    )
    assert config.workspace_id == "test_workspace"
    assert config.max_total_tokens == 4096
    print("✓ WorkspaceConfig creation works")
    return True


def test_allocator_initialization():
    """Test MemoryBudgetAllocator initialization."""
    allocator = MemoryBudgetAllocator()
    assert allocator.default_config is not None
    assert "default" in allocator.workspace_configs
    print("✓ MemoryBudgetAllocator initialization works")
    return True


def test_query_complexity_estimation():
    """Test query complexity estimation."""
    allocator = MemoryBudgetAllocator(log_allocations=False)
    
    # Test simple query
    complexity = allocator.estimate_query_complexity("Hello")
    assert complexity == QueryComplexity.SIMPLE
    
    # Test medium query
    complexity = allocator.estimate_query_complexity("How do I implement this?")
    assert complexity in [QueryComplexity.SIMPLE, QueryComplexity.MEDIUM]
    
    # Test complex query
    complexity = allocator.estimate_query_complexity(
        "Explain the differences between synchronous and asynchronous programming"
    )
    assert complexity in [QueryComplexity.MEDIUM, QueryComplexity.COMPLEX]
    
    print("✓ Query complexity estimation works")
    return True


def test_memory_scoring():
    """Test memory scoring calculation."""
    allocator = MemoryBudgetAllocator(log_allocations=False)
    config = WorkspaceConfig(workspace_id="test")
    
    item = MemoryItem(
        memory_id="m1",
        text="Test memory",
        tier=MemoryTier.WORKING,
        timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
        relevance_score=0.9,
        importance_score=0.8
    )
    
    score = allocator.calculate_memory_score(item, config)
    assert 0.0 <= score <= 1.0
    assert item.freshness_score > 0.9  # Should be fresh (1 hour old)
    assert item.combined_score == score
    
    print(f"✓ Memory scoring works (score: {score:.4f})")
    return True


def test_budget_allocation():
    """Test memory budget allocation."""
    allocator = MemoryBudgetAllocator(log_allocations=False)
    
    # Create test memories
    now = datetime.now(timezone.utc)
    memories = [
        MemoryItem(
            memory_id="m1",
            text="Working memory item - very recent",
            tier=MemoryTier.WORKING,
            timestamp=now - timedelta(hours=1),
            relevance_score=0.9,
            importance_score=0.8
        ),
        MemoryItem(
            memory_id="m2",
            text="Project memory item - from yesterday",
            tier=MemoryTier.PROJECT,
            timestamp=now - timedelta(days=1),
            relevance_score=0.7,
            importance_score=0.8
        ),
    ]
    
    result = allocator.allocate_memory_budget(
        query="How do I optimize this?",
        available_memories=memories
    )
    
    assert "complexity" in result
    assert "total_tokens_allocated" in result
    assert "total_memories_selected" in result
    assert "tiers" in result
    assert result["total_memories_selected"] <= len(memories)
    
    print(f"✓ Budget allocation works (complexity: {result['complexity']}, "
          f"tokens: {result['total_tokens_allocated']}, "
          f"memories: {result['total_memories_selected']})")
    return True


def test_promotion_demotion():
    """Test promotion/demotion evaluation."""
    allocator = MemoryBudgetAllocator(log_allocations=False)
    config = WorkspaceConfig(workspace_id="test")
    
    now = datetime.now(timezone.utc)
    
    # High-performing memory
    high_perf = MemoryItem(
        memory_id="high",
        text="Frequently accessed",
        tier=MemoryTier.PROJECT,
        timestamp=now - timedelta(hours=12),
        relevance_score=0.9,
        importance_score=0.9,
        access_count=5,
        last_accessed=now - timedelta(minutes=10)
    )
    
    # Low-performing memory
    low_perf = MemoryItem(
        memory_id="low",
        text="Rarely used",
        tier=MemoryTier.WORKING,
        timestamp=now - timedelta(days=7),
        relevance_score=0.3,
        importance_score=0.2,
        access_count=0,
        last_accessed=None
    )
    
    # Score memories first
    allocator.calculate_memory_score(high_perf, config)
    allocator.calculate_memory_score(low_perf, config)
    
    result = allocator.evaluate_promotion_demotion([high_perf, low_perf], config)
    
    assert "promotions" in result
    assert "demotions" in result
    assert "total_evaluated" in result
    assert result["total_evaluated"] == 2
    
    print(f"✓ Promotion/demotion works (promotions: {len(result['promotions'])}, "
          f"demotions: {len(result['demotions'])})")
    return True


def test_workspace_registration():
    """Test registering custom workspace."""
    allocator = MemoryBudgetAllocator(log_allocations=False)
    
    custom_config = WorkspaceConfig(
        workspace_id="custom",
        max_total_tokens=16384,
        working_memory_pct=0.50
    )
    
    allocator.register_workspace(custom_config)
    assert "custom" in allocator.workspace_configs
    
    print("✓ Workspace registration works")
    return True


def test_project_registration_and_resolution():
    """Test registering and resolving project-level configuration overrides."""
    allocator = MemoryBudgetAllocator(log_allocations=False)

    project_config = WorkspaceConfig(
        workspace_id="default",
        max_total_tokens=10000,
        project_memory_pct=0.35,
        working_memory_pct=0.30,
        long_term_memory_pct=0.15,
        rag_memory_pct=0.20
    )

    allocator.register_project("default", "brainego-core", project_config)

    resolved, scope = allocator.resolve_config("default", "brainego-core")
    assert scope == "project"
    assert resolved.max_total_tokens == 10000

    resolved_workspace, scope_workspace = allocator.resolve_config("default", None)
    assert scope_workspace == "workspace"
    assert resolved_workspace.workspace_id == "default"

    print("✓ Project registration and config resolution works")
    return True


def test_config_loader():
    """Test configuration loader."""
    try:
        from memory_budget_config_loader import MemoryBudgetConfigLoader
        
        # Test loading from YAML
        configs = MemoryBudgetConfigLoader.load_from_yaml('configs/memory-budget.yaml')
        
        assert len(configs) > 0
        assert "default" in configs
        assert isinstance(configs["default"], WorkspaceConfig)

        project_overrides = MemoryBudgetConfigLoader.load_project_overrides(
            'configs/memory-budget.yaml'
        )
        assert "default" in project_overrides
        assert "brainego-core" in project_overrides["default"]
        assert isinstance(project_overrides["default"]["brainego-core"], WorkspaceConfig)
        
        print(f"✓ Config loader works (loaded {len(configs)} workspaces)")
        return True
    except FileNotFoundError:
        print("⚠ Config file not found (skipping config loader test)")
        return True
    except Exception as e:
        print(f"✗ Config loader failed: {e}")
        return False


def test_allocation_statistics():
    """Test allocation statistics."""
    allocator = MemoryBudgetAllocator(log_allocations=False)
    
    # Perform some allocations
    now = datetime.now(timezone.utc)
    memories = [
        MemoryItem(
            memory_id="m1",
            text="Test memory",
            tier=MemoryTier.WORKING,
            timestamp=now,
            relevance_score=0.8,
            importance_score=0.7
        )
    ]
    
    for query in ["Query 1", "Query 2"]:
        allocator.allocate_memory_budget(query, memories.copy())
    
    stats = allocator.get_allocation_statistics()
    
    assert "total_allocations" in stats
    assert stats["total_allocations"] == 2
    assert "averages" in stats
    
    print(f"✓ Allocation statistics works (allocations: {stats['total_allocations']})")
    return True


def test_allocation_contains_budget_scope_metadata():
    """Test allocation metadata includes budget source and project context."""
    allocator = MemoryBudgetAllocator(log_allocations=False)
    now = datetime.now(timezone.utc)
    memories = [
        MemoryItem(
            memory_id="m1",
            text="A memory item for budget metadata checks",
            tier=MemoryTier.PROJECT,
            timestamp=now,
            relevance_score=0.9,
            importance_score=0.8,
        )
    ]

    project_config = WorkspaceConfig(
        workspace_id="default",
        max_total_tokens=12000,
        working_memory_pct=0.30,
        project_memory_pct=0.35,
        long_term_memory_pct=0.15,
        rag_memory_pct=0.20
    )
    allocator.register_project("default", "brainego-core", project_config)

    result = allocator.allocate_memory_budget(
        query="Summarize current design constraints",
        available_memories=memories,
        workspace_id="default",
        project_id="brainego-core",
    )

    assert result["project_id"] == "brainego-core"
    assert result["config_scope"] == "project"
    assert "budget" in result
    assert result["budget"]["max_total_tokens"] == 12000

    print("✓ Allocation metadata includes project scope and budget details")
    return True


def run_all_tests():
    """Run all tests."""
    tests = [
        test_imports,
        test_memory_item_creation,
        test_workspace_config,
        test_allocator_initialization,
        test_query_complexity_estimation,
        test_memory_scoring,
        test_budget_allocation,
        test_promotion_demotion,
        test_workspace_registration,
        test_config_loader,
        test_allocation_statistics,
    ]
    
    print("=" * 70)
    print("Running Memory Budget Allocator Tests")
    print("=" * 70)
    print()
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1
    
    print()
    print("=" * 70)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
