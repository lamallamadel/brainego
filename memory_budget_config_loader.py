#!/usr/bin/env python3
"""
Configuration loader for MemoryBudgetAllocator from YAML files.
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from memory_budget_allocator import WorkspaceConfig, QueryComplexity

logger = logging.getLogger(__name__)


class MemoryBudgetConfigLoader:
    """Load and manage workspace configurations from YAML files."""
    
    @staticmethod
    def load_from_yaml(filepath: str) -> Dict[str, WorkspaceConfig]:
        """
        Load workspace configurations from YAML file.
        
        Args:
            filepath: Path to YAML configuration file
        
        Returns:
            Dictionary mapping workspace_id to WorkspaceConfig
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Configuration file not found: {filepath}")
        
        with open(filepath, 'r') as f:
            yaml_data = yaml.safe_load(f)
        
        configs = {}
        
        # Parse each workspace configuration
        for workspace_id, workspace_data in yaml_data.items():
            # Skip non-workspace sections
            if workspace_id in ['logging', 'performance']:
                continue
            
            try:
                config = MemoryBudgetConfigLoader._parse_workspace_config(
                    workspace_id,
                    workspace_data
                )
                configs[workspace_id] = config
                logger.info(f"Loaded configuration for workspace: {workspace_id}")
            except Exception as e:
                logger.error(f"Error parsing workspace '{workspace_id}': {e}")
                raise
        
        return configs
    
    @staticmethod
    def _parse_workspace_config(
        workspace_id: str,
        data: Dict[str, Any]
    ) -> WorkspaceConfig:
        """Parse workspace configuration from YAML data."""
        
        # Get tier allocation percentages
        tier_alloc = data.get('tier_allocation', {})
        
        # Get complexity multipliers
        complexity_mult = data.get('complexity_multipliers', {})
        complexity_multipliers = {
            QueryComplexity.SIMPLE: complexity_mult.get('simple', 0.5),
            QueryComplexity.MEDIUM: complexity_mult.get('medium', 1.0),
            QueryComplexity.COMPLEX: complexity_mult.get('complex', 1.5),
            QueryComplexity.EXPERT: complexity_mult.get('expert', 2.0)
        }
        
        # Get scoring weights
        scoring_weights = data.get('scoring_weights', {})
        
        # Get freshness configuration
        freshness_config = data.get('freshness', {})
        
        # Get promotion/demotion configuration
        promotion_config = data.get('promotion', {})
        demotion_config = data.get('demotion', {})
        
        # Create WorkspaceConfig
        config = WorkspaceConfig(
            workspace_id=workspace_id,
            max_total_tokens=data.get('max_total_tokens', 8192),
            working_memory_pct=tier_alloc.get('working_memory_pct', 0.30),
            project_memory_pct=tier_alloc.get('project_memory_pct', 0.25),
            long_term_memory_pct=tier_alloc.get('long_term_memory_pct', 0.20),
            rag_memory_pct=tier_alloc.get('rag_memory_pct', 0.25),
            complexity_multipliers=complexity_multipliers,
            relevance_weight=scoring_weights.get('relevance', 0.5),
            importance_weight=scoring_weights.get('importance', 0.3),
            freshness_weight=scoring_weights.get('freshness', 0.2),
            freshness_half_life_hours=freshness_config.get('half_life_hours', 168.0),
            promotion_threshold=promotion_config.get('threshold', 0.8),
            demotion_threshold=demotion_config.get('threshold', 0.3),
            promotion_access_threshold=promotion_config.get('access_threshold', 3),
            tokens_per_char=data.get('tokens_per_char', 0.25)
        )
        
        # Validate configuration
        MemoryBudgetConfigLoader._validate_config(config)
        
        return config
    
    @staticmethod
    def _validate_config(config: WorkspaceConfig):
        """Validate workspace configuration."""
        
        # Validate tier allocation percentages sum to 1.0
        total_pct = (
            config.working_memory_pct +
            config.project_memory_pct +
            config.long_term_memory_pct +
            config.rag_memory_pct
        )
        
        if abs(total_pct - 1.0) > 0.01:  # Allow small floating point errors
            raise ValueError(
                f"Tier allocation percentages must sum to 1.0, got {total_pct} "
                f"for workspace '{config.workspace_id}'"
            )
        
        # Validate scoring weights sum to 1.0
        total_weight = (
            config.relevance_weight +
            config.importance_weight +
            config.freshness_weight
        )
        
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(
                f"Scoring weights must sum to 1.0, got {total_weight} "
                f"for workspace '{config.workspace_id}'"
            )
        
        # Validate thresholds are in valid range
        if not 0 <= config.promotion_threshold <= 1:
            raise ValueError(
                f"Promotion threshold must be between 0 and 1, "
                f"got {config.promotion_threshold} for workspace '{config.workspace_id}'"
            )
        
        if not 0 <= config.demotion_threshold <= 1:
            raise ValueError(
                f"Demotion threshold must be between 0 and 1, "
                f"got {config.demotion_threshold} for workspace '{config.workspace_id}'"
            )
        
        # Validate max_total_tokens is positive
        if config.max_total_tokens <= 0:
            raise ValueError(
                f"max_total_tokens must be positive, "
                f"got {config.max_total_tokens} for workspace '{config.workspace_id}'"
            )
        
        logger.debug(f"Configuration validated successfully: {config.workspace_id}")
    
    @staticmethod
    def load_workspace_config(
        filepath: str,
        workspace_id: str
    ) -> Optional[WorkspaceConfig]:
        """
        Load a specific workspace configuration from YAML file.
        
        Args:
            filepath: Path to YAML configuration file
            workspace_id: Workspace identifier to load
        
        Returns:
            WorkspaceConfig if found, None otherwise
        """
        configs = MemoryBudgetConfigLoader.load_from_yaml(filepath)
        return configs.get(workspace_id)
    
    @staticmethod
    def get_logging_config(filepath: str) -> Dict[str, Any]:
        """
        Get logging configuration from YAML file.
        
        Args:
            filepath: Path to YAML configuration file
        
        Returns:
            Logging configuration dictionary
        """
        with open(filepath, 'r') as f:
            yaml_data = yaml.safe_load(f)
        
        return yaml_data.get('logging', {
            'enable_allocation_logging': True,
            'log_level': 'INFO',
            'export_directory': './logs/allocations'
        })
    
    @staticmethod
    def get_performance_config(filepath: str) -> Dict[str, Any]:
        """
        Get performance configuration from YAML file.
        
        Args:
            filepath: Path to YAML configuration file
        
        Returns:
            Performance configuration dictionary
        """
        with open(filepath, 'r') as f:
            yaml_data = yaml.safe_load(f)
        
        return yaml_data.get('performance', {
            'track_history': True,
            'max_history_size': 1000,
            'auto_export_interval': 3600
        })


def example_usage():
    """Example usage of configuration loader."""
    
    # Load all workspace configurations
    configs = MemoryBudgetConfigLoader.load_from_yaml('configs/memory-budget.yaml')
    
    print(f"Loaded {len(configs)} workspace configurations:")
    for workspace_id, config in configs.items():
        print(f"\n{workspace_id}:")
        print(f"  Max tokens: {config.max_total_tokens}")
        print(f"  Tier allocation:")
        print(f"    Working: {config.working_memory_pct * 100:.0f}%")
        print(f"    Project: {config.project_memory_pct * 100:.0f}%")
        print(f"    Long-term: {config.long_term_memory_pct * 100:.0f}%")
        print(f"    RAG: {config.rag_memory_pct * 100:.0f}%")
    
    # Load specific workspace
    dev_config = MemoryBudgetConfigLoader.load_workspace_config(
        'configs/memory-budget.yaml',
        'development'
    )
    
    if dev_config:
        print(f"\nDevelopment workspace loaded:")
        print(f"  Max tokens: {dev_config.max_total_tokens}")
        print(f"  Freshness half-life: {dev_config.freshness_half_life_hours} hours")
    
    # Load logging configuration
    logging_config = MemoryBudgetConfigLoader.get_logging_config(
        'configs/memory-budget.yaml'
    )
    print(f"\nLogging configuration: {logging_config}")


if __name__ == "__main__":
    example_usage()
