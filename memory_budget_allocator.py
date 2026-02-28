#!/usr/bin/env python3
"""
Memory Budget Allocator with query complexity estimation, dynamic token allocation,
Mem0 scoring with relevance×importance×freshness formula, and promotion/demotion
mechanism for memory items.
"""

import logging
import math
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
import json

logger = logging.getLogger(__name__)


class MemoryTier(Enum):
    """Memory storage tiers for different time horizons."""
    WORKING = "working"  # Very recent, high-priority context
    PROJECT = "project"  # Current project/session context
    LONG_TERM = "long_term"  # Historical facts and patterns
    RAG = "rag"  # Retrieved documents/knowledge base


class QueryComplexity(Enum):
    """Query complexity levels for token budget estimation."""
    SIMPLE = "simple"  # Basic queries, minimal context needed
    MEDIUM = "medium"  # Standard queries, moderate context
    COMPLEX = "complex"  # Complex queries, extensive context
    EXPERT = "expert"  # Expert-level queries, maximum context


@dataclass
class MemoryItem:
    """Represents a memory item with scoring metadata."""
    memory_id: str
    text: str
    tier: MemoryTier
    timestamp: datetime
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Scoring components
    relevance_score: float = 0.0  # Cosine similarity to query
    importance_score: float = 0.5  # Intrinsic importance (0-1)
    freshness_score: float = 1.0  # Time-based freshness (0-1)
    
    # Combined score
    combined_score: float = 0.0
    
    # Token usage
    token_count: int = 0
    
    # Promotion/demotion tracking
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    promotion_score: float = 0.0


@dataclass
class WorkspaceConfig:
    """Workspace-specific budget configuration."""
    workspace_id: str
    
    # Total budget constraints
    max_total_tokens: int = 8192
    
    # Tier-specific budgets (percentage of total)
    working_memory_pct: float = 0.30  # 30% for immediate context
    project_memory_pct: float = 0.25  # 25% for project context
    long_term_memory_pct: float = 0.20  # 20% for historical facts
    rag_memory_pct: float = 0.25  # 25% for retrieved documents
    
    # Query complexity multipliers
    complexity_multipliers: Dict[QueryComplexity, float] = field(default_factory=lambda: {
        QueryComplexity.SIMPLE: 0.5,
        QueryComplexity.MEDIUM: 1.0,
        QueryComplexity.COMPLEX: 1.5,
        QueryComplexity.EXPERT: 2.0
    })
    
    # Scoring weights (must sum to 1.0)
    relevance_weight: float = 0.5
    importance_weight: float = 0.3
    freshness_weight: float = 0.2
    
    # Freshness decay parameters
    freshness_half_life_hours: float = 168.0  # 1 week
    
    # Promotion/demotion thresholds
    promotion_threshold: float = 0.8  # Score needed for tier promotion
    demotion_threshold: float = 0.3  # Score below which item is demoted
    promotion_access_threshold: int = 3  # Min accesses for promotion consideration
    
    # Token counting parameters
    tokens_per_char: float = 0.25  # Approximate tokens per character
    
    def get_tier_budget(self, tier: MemoryTier, complexity: QueryComplexity) -> int:
        """Calculate token budget for a specific tier and query complexity."""
        base_budget = self.max_total_tokens * self._get_tier_percentage(tier)
        multiplier = self.complexity_multipliers.get(complexity, 1.0)
        return int(base_budget * multiplier)
    
    def _get_tier_percentage(self, tier: MemoryTier) -> float:
        """Get percentage allocation for a tier."""
        tier_map = {
            MemoryTier.WORKING: self.working_memory_pct,
            MemoryTier.PROJECT: self.project_memory_pct,
            MemoryTier.LONG_TERM: self.long_term_memory_pct,
            MemoryTier.RAG: self.rag_memory_pct
        }
        return tier_map.get(tier, 0.0)


class MemoryBudgetAllocator:
    """
    Memory budget allocator with query complexity estimation, dynamic token allocation,
    Mem0 scoring, and promotion/demotion mechanism.
    
    Features:
    - Query complexity estimation based on content analysis
    - Dynamic token allocation across memory tiers
    - Mem0 scoring: relevance × importance × freshness
    - Automatic promotion/demotion of memory items
    - Workspace-specific budget configuration
    - Comprehensive allocation logging
    """
    
    def __init__(
        self,
        default_config: Optional[WorkspaceConfig] = None,
        log_allocations: bool = True
    ):
        """
        Initialize Memory Budget Allocator.
        
        Args:
            default_config: Default workspace configuration
            log_allocations: Whether to log allocation decisions
        """
        self.default_config = default_config or WorkspaceConfig(workspace_id="default")
        self.workspace_configs: Dict[str, WorkspaceConfig] = {
            "default": self.default_config
        }
        self.project_configs: Dict[Tuple[str, str], WorkspaceConfig] = {}
        self.log_allocations = log_allocations
        
        # Allocation history for analysis
        self.allocation_history: List[Dict[str, Any]] = []
        
        logger.info("Memory Budget Allocator initialized")
    
    def register_workspace(self, config: WorkspaceConfig):
        """Register a workspace-specific configuration."""
        self.workspace_configs[config.workspace_id] = config
        logger.info(f"Registered workspace config: {config.workspace_id}")

    def register_project(self, workspace_id: str, project_id: str, config: WorkspaceConfig):
        """Register a project-specific configuration override within a workspace."""
        self.project_configs[(workspace_id, project_id)] = config
        logger.info(
            "Registered project config: workspace=%s, project=%s",
            workspace_id,
            project_id
        )

    def resolve_config(
        self,
        workspace_id: str,
        project_id: Optional[str] = None
    ) -> Tuple[WorkspaceConfig, str]:
        """
        Resolve effective configuration for a request.

        Priority:
        1) Project-level config (workspace + project)
        2) Workspace-level config
        3) Default config
        """
        if project_id:
            project_key = (workspace_id, project_id)
            if project_key in self.project_configs:
                return self.project_configs[project_key], "project"

        if workspace_id in self.workspace_configs:
            return self.workspace_configs[workspace_id], "workspace"

        return self.default_config, "default"
    
    def estimate_query_complexity(self, query: str, context: Optional[Dict[str, Any]] = None) -> QueryComplexity:
        """
        Estimate query complexity based on content analysis.
        
        Args:
            query: Query text
            context: Optional context (conversation history, metadata)
        
        Returns:
            Estimated query complexity level
        """
        # Length-based factors
        query_length = len(query.split())
        
        # Keyword-based complexity indicators
        expert_keywords = [
            'explain', 'analyze', 'compare', 'evaluate', 'synthesize',
            'architecture', 'design', 'optimize', 'debug', 'implement'
        ]
        complex_keywords = [
            'how', 'why', 'what if', 'difference', 'relationship',
            'between', 'impact', 'effect', 'cause'
        ]
        
        query_lower = query.lower()
        expert_matches = sum(1 for kw in expert_keywords if kw in query_lower)
        complex_matches = sum(1 for kw in complex_keywords if kw in query_lower)
        
        # Context-based factors
        has_conversation_history = context and context.get('history_length', 0) > 5
        has_multi_turn = context and context.get('turn_count', 0) > 3
        requires_retrieval = context and context.get('requires_retrieval', False)
        
        # Scoring
        complexity_score = 0
        
        # Length factor
        if query_length > 50:
            complexity_score += 3
        elif query_length > 20:
            complexity_score += 2
        elif query_length > 10:
            complexity_score += 1
        
        # Keyword factor
        complexity_score += expert_matches * 2
        complexity_score += complex_matches
        
        # Context factor
        if has_conversation_history:
            complexity_score += 1
        if has_multi_turn:
            complexity_score += 1
        if requires_retrieval:
            complexity_score += 2
        
        # Determine complexity level
        if complexity_score >= 8:
            complexity = QueryComplexity.EXPERT
        elif complexity_score >= 5:
            complexity = QueryComplexity.COMPLEX
        elif complexity_score >= 2:
            complexity = QueryComplexity.MEDIUM
        else:
            complexity = QueryComplexity.SIMPLE
        
        if self.log_allocations:
            logger.info(
                f"Query complexity estimated: {complexity.value} "
                f"(score={complexity_score}, length={query_length})"
            )
        
        return complexity
    
    def calculate_memory_score(
        self,
        item: MemoryItem,
        config: WorkspaceConfig,
        current_time: Optional[datetime] = None
    ) -> float:
        """
        Calculate combined memory score using Mem0 formula:
        score = relevance × importance × freshness
        
        Args:
            item: Memory item to score
            config: Workspace configuration
            current_time: Current time for freshness calculation
        
        Returns:
            Combined score (0-1)
        """
        current_time = current_time or datetime.now(timezone.utc)
        
        # Calculate freshness score based on exponential decay
        if item.timestamp:
            time_diff = (current_time - item.timestamp).total_seconds() / 3600  # hours
            half_life = config.freshness_half_life_hours
            item.freshness_score = math.exp(-0.693 * time_diff / half_life)
        else:
            item.freshness_score = 1.0
        
        # Apply Mem0 scoring formula with configured weights
        weighted_score = (
            item.relevance_score * config.relevance_weight +
            item.importance_score * config.importance_weight +
            item.freshness_score * config.freshness_weight
        )
        
        # Alternative: multiplicative formula (commented out)
        # multiplicative_score = (
        #     item.relevance_score * 
        #     item.importance_score * 
        #     item.freshness_score
        # ) ** (1/3)  # Geometric mean
        
        item.combined_score = max(0.0, min(1.0, weighted_score))
        
        return item.combined_score
    
    def estimate_token_count(self, text: str, config: WorkspaceConfig) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to estimate
            config: Workspace configuration
        
        Returns:
            Estimated token count
        """
        return int(len(text) * config.tokens_per_char)
    
    def allocate_memory_budget(
        self,
        query: str,
        available_memories: List[MemoryItem],
        workspace_id: str = "default",
        project_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Allocate memory budget across tiers based on query complexity and memory scores.
        
        Args:
            query: Query text
            available_memories: List of available memory items
            workspace_id: Workspace identifier
            context: Optional query context
        
        Returns:
            Allocation result with selected memories per tier
        """
        start_time = time.time()
        
        # Resolve configuration (project -> workspace -> default)
        config, config_scope = self.resolve_config(workspace_id, project_id)
        
        # Estimate query complexity
        complexity = self.estimate_query_complexity(query, context)
        
        # Calculate token counts for memories
        for item in available_memories:
            if item.token_count == 0:
                item.token_count = self.estimate_token_count(item.text, config)
        
        # Score all memories
        current_time = datetime.now(timezone.utc)
        for item in available_memories:
            self.calculate_memory_score(item, config, current_time)
        
        # Group memories by tier
        memories_by_tier: Dict[MemoryTier, List[MemoryItem]] = {
            tier: [] for tier in MemoryTier
        }
        for item in available_memories:
            memories_by_tier[item.tier].append(item)
        
        # Allocate per tier
        allocation_result = {
            "query": query,
            "workspace_id": workspace_id,
            "project_id": project_id,
            "config_scope": config_scope,
            "complexity": complexity.value,
            "timestamp": current_time.isoformat(),
            "tiers": {},
            "budget": {
                "max_total_tokens": config.max_total_tokens,
                "tier_percentages": {
                    MemoryTier.WORKING.value: config.working_memory_pct,
                    MemoryTier.PROJECT.value: config.project_memory_pct,
                    MemoryTier.LONG_TERM.value: config.long_term_memory_pct,
                    MemoryTier.RAG.value: config.rag_memory_pct,
                },
                "complexity_multiplier": config.complexity_multipliers.get(complexity, 1.0)
            },
            "total_tokens_allocated": 0,
            "total_memories_selected": 0,
            "processing_time_ms": 0
        }
        
        for tier in MemoryTier:
            tier_memories = memories_by_tier[tier]
            tier_budget = config.get_tier_budget(tier, complexity)
            
            # Sort memories by combined score (descending)
            tier_memories.sort(key=lambda x: x.combined_score, reverse=True)
            
            # Select memories within budget
            selected_memories = []
            tokens_used = 0
            
            for item in tier_memories:
                if tokens_used + item.token_count <= tier_budget:
                    selected_memories.append(item)
                    tokens_used += item.token_count
                    
                    # Update access tracking
                    item.access_count += 1
                    item.last_accessed = current_time
            
            # Store tier allocation results
            allocation_result["tiers"][tier.value] = {
                "budget_tokens": tier_budget,
                "tokens_used": tokens_used,
                "tokens_remaining": tier_budget - tokens_used,
                "memories_available": len(tier_memories),
                "memories_selected": len(selected_memories),
                "utilization_pct": round(100 * tokens_used / tier_budget, 2) if tier_budget > 0 else 0,
                "selected_memories": [
                    {
                        "memory_id": m.memory_id,
                        "text_preview": m.text[:100] + "..." if len(m.text) > 100 else m.text,
                        "token_count": m.token_count,
                        "combined_score": round(m.combined_score, 4),
                        "relevance_score": round(m.relevance_score, 4),
                        "importance_score": round(m.importance_score, 4),
                        "freshness_score": round(m.freshness_score, 4),
                        "access_count": m.access_count,
                        "timestamp": m.timestamp.isoformat() if m.timestamp else None
                    }
                    for m in selected_memories
                ]
            }
            
            allocation_result["total_tokens_allocated"] += tokens_used
            allocation_result["total_memories_selected"] += len(selected_memories)
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000
        allocation_result["processing_time_ms"] = round(processing_time, 2)
        
        # Log allocation
        if self.log_allocations:
            self._log_allocation(allocation_result)
        
        # Store in history
        self.allocation_history.append(allocation_result)
        
        return allocation_result
    
    def evaluate_promotion_demotion(
        self,
        items: List[MemoryItem],
        config: WorkspaceConfig
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Evaluate memory items for promotion or demotion between tiers.
        
        Args:
            items: Memory items to evaluate
            config: Workspace configuration
        
        Returns:
            Dictionary with promotion and demotion recommendations
        """
        promotions = []
        demotions = []
        
        # Calculate promotion scores based on access patterns and performance
        for item in items:
            # Promotion score factors:
            # 1. Combined score (relevance × importance × freshness)
            # 2. Access frequency
            # 3. Recency of access
            
            access_factor = min(1.0, item.access_count / config.promotion_access_threshold)
            
            recency_factor = 1.0
            if item.last_accessed:
                hours_since_access = (
                    datetime.now(timezone.utc) - item.last_accessed
                ).total_seconds() / 3600
                recency_factor = math.exp(-0.1 * hours_since_access / 24)  # Decay over days
            
            item.promotion_score = (
                item.combined_score * 0.5 +
                access_factor * 0.3 +
                recency_factor * 0.2
            )
            
            # Evaluate for promotion (move to higher-priority tier)
            if item.promotion_score >= config.promotion_threshold:
                if item.access_count >= config.promotion_access_threshold:
                    target_tier = self._get_promotion_tier(item.tier)
                    if target_tier != item.tier:
                        promotions.append({
                            "memory_id": item.memory_id,
                            "current_tier": item.tier.value,
                            "target_tier": target_tier.value,
                            "promotion_score": round(item.promotion_score, 4),
                            "access_count": item.access_count,
                            "combined_score": round(item.combined_score, 4),
                            "reason": "High performance and frequent access"
                        })
            
            # Evaluate for demotion (move to lower-priority tier)
            elif item.promotion_score < config.demotion_threshold:
                target_tier = self._get_demotion_tier(item.tier)
                if target_tier != item.tier:
                    demotions.append({
                        "memory_id": item.memory_id,
                        "current_tier": item.tier.value,
                        "target_tier": target_tier.value,
                        "promotion_score": round(item.promotion_score, 4),
                        "access_count": item.access_count,
                        "combined_score": round(item.combined_score, 4),
                        "reason": "Low performance or infrequent access"
                    })
        
        result = {
            "promotions": promotions,
            "demotions": demotions,
            "total_evaluated": len(items),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if self.log_allocations:
            logger.info(
                f"Promotion/Demotion evaluation: "
                f"{len(promotions)} promotions, {len(demotions)} demotions "
                f"out of {len(items)} items"
            )
        
        return result
    
    def _get_promotion_tier(self, current_tier: MemoryTier) -> MemoryTier:
        """Get target tier for promotion."""
        tier_hierarchy = [
            MemoryTier.LONG_TERM,
            MemoryTier.RAG,
            MemoryTier.PROJECT,
            MemoryTier.WORKING
        ]
        
        try:
            current_idx = tier_hierarchy.index(current_tier)
            if current_idx < len(tier_hierarchy) - 1:
                return tier_hierarchy[current_idx + 1]
        except (ValueError, IndexError):
            pass
        
        return current_tier
    
    def _get_demotion_tier(self, current_tier: MemoryTier) -> MemoryTier:
        """Get target tier for demotion."""
        tier_hierarchy = [
            MemoryTier.LONG_TERM,
            MemoryTier.RAG,
            MemoryTier.PROJECT,
            MemoryTier.WORKING
        ]
        
        try:
            current_idx = tier_hierarchy.index(current_tier)
            if current_idx > 0:
                return tier_hierarchy[current_idx - 1]
        except (ValueError, IndexError):
            pass
        
        return current_tier
    
    def _log_allocation(self, allocation: Dict[str, Any]):
        """Log allocation decision details."""
        logger.info(
            f"Memory Budget Allocation - "
            f"Workspace: {allocation['workspace_id']}, "
            f"Project: {allocation.get('project_id') or 'n/a'}, "
            f"Scope: {allocation.get('config_scope', 'unknown')}, "
            f"Complexity: {allocation['complexity']}, "
            f"Tokens: {allocation['total_tokens_allocated']}, "
            f"Memories: {allocation['total_memories_selected']}, "
            f"Time: {allocation['processing_time_ms']}ms"
        )
        
        for tier_name, tier_data in allocation["tiers"].items():
            logger.debug(
                f"  Tier {tier_name}: "
                f"{tier_data['tokens_used']}/{tier_data['budget_tokens']} tokens "
                f"({tier_data['utilization_pct']}% utilized), "
                f"{tier_data['memories_selected']}/{tier_data['memories_available']} memories"
            )
    
    def get_allocation_statistics(
        self,
        workspace_id: Optional[str] = None,
        time_window_hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get allocation statistics for analysis.
        
        Args:
            workspace_id: Optional workspace filter
            time_window_hours: Optional time window for recent stats
        
        Returns:
            Allocation statistics
        """
        filtered_history = self.allocation_history
        
        # Filter by workspace
        if workspace_id:
            filtered_history = [
                a for a in filtered_history
                if a.get("workspace_id") == workspace_id
            ]
        
        # Filter by time window
        if time_window_hours:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)
            filtered_history = [
                a for a in filtered_history
                if datetime.fromisoformat(a["timestamp"]) >= cutoff_time
            ]
        
        if not filtered_history:
            return {
                "total_allocations": 0,
                "message": "No allocation history available"
            }
        
        # Calculate statistics
        total_allocations = len(filtered_history)
        avg_tokens = sum(a["total_tokens_allocated"] for a in filtered_history) / total_allocations
        avg_memories = sum(a["total_memories_selected"] for a in filtered_history) / total_allocations
        avg_time = sum(a["processing_time_ms"] for a in filtered_history) / total_allocations
        
        # Complexity distribution
        complexity_counts = {}
        for a in filtered_history:
            complexity = a.get("complexity", "unknown")
            complexity_counts[complexity] = complexity_counts.get(complexity, 0) + 1
        
        # Tier utilization
        tier_stats = {}
        for tier in MemoryTier:
            tier_name = tier.value
            tier_allocations = [
                a["tiers"].get(tier_name, {})
                for a in filtered_history
                if tier_name in a.get("tiers", {})
            ]
            
            if tier_allocations:
                tier_stats[tier_name] = {
                    "avg_utilization_pct": sum(
                        t.get("utilization_pct", 0) for t in tier_allocations
                    ) / len(tier_allocations),
                    "avg_memories_selected": sum(
                        t.get("memories_selected", 0) for t in tier_allocations
                    ) / len(tier_allocations),
                    "avg_tokens_used": sum(
                        t.get("tokens_used", 0) for t in tier_allocations
                    ) / len(tier_allocations)
                }
        
        return {
            "total_allocations": total_allocations,
            "workspace_id": workspace_id or "all",
            "time_window_hours": time_window_hours,
            "averages": {
                "tokens_allocated": round(avg_tokens, 2),
                "memories_selected": round(avg_memories, 2),
                "processing_time_ms": round(avg_time, 2)
            },
            "complexity_distribution": complexity_counts,
            "tier_statistics": tier_stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def export_allocation_log(self, filepath: str):
        """Export allocation history to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.allocation_history, f, indent=2, default=str)
        logger.info(f"Exported {len(self.allocation_history)} allocations to {filepath}")
    
    def clear_allocation_history(self):
        """Clear allocation history."""
        count = len(self.allocation_history)
        self.allocation_history.clear()
        logger.info(f"Cleared {count} allocation records")
