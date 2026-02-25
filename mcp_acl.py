#!/usr/bin/env python3
"""
MCP Access Control List (ACL) Manager.

Handles authorization and permission checking for MCP operations.
"""

import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
import redis

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter using Redis."""
    
    def __init__(self, redis_client: redis.Redis, key_prefix: str = "rate_limit"):
        self.redis = redis_client
        self.key_prefix = key_prefix
    
    def check_rate_limit(
        self, 
        identifier: str, 
        limit_per_minute: int, 
        limit_per_hour: int
    ) -> tuple[bool, Optional[str]]:
        """
        Check if request is within rate limits.
        
        Returns:
            (allowed, reason) tuple
        """
        now = datetime.utcnow()
        minute_key = f"{self.key_prefix}:{identifier}:minute:{now.strftime('%Y%m%d%H%M')}"
        hour_key = f"{self.key_prefix}:{identifier}:hour:{now.strftime('%Y%m%d%H')}"
        
        # Check minute limit
        minute_count = self.redis.incr(minute_key)
        if minute_count == 1:
            self.redis.expire(minute_key, 60)
        
        if minute_count > limit_per_minute:
            return False, f"Rate limit exceeded: {limit_per_minute} requests per minute"
        
        # Check hour limit
        hour_count = self.redis.incr(hour_key)
        if hour_count == 1:
            self.redis.expire(hour_key, 3600)
        
        if hour_count > limit_per_hour:
            return False, f"Rate limit exceeded: {limit_per_hour} requests per hour"
        
        return True, None
    
    def reset_limits(self, identifier: str):
        """Reset rate limits for an identifier."""
        pattern = f"{self.key_prefix}:{identifier}:*"
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)


class MCPACLManager:
    """Manages access control for MCP operations."""
    
    def __init__(
        self, 
        acl_config: Dict[str, Any], 
        redis_client: Optional[redis.Redis] = None
    ):
        self.acl_config = acl_config
        self.roles = acl_config.get("roles", {})
        self.default_role = acl_config.get("default_role", "readonly")
        self.api_key_roles = acl_config.get("api_key_roles", {})
        self.user_roles = acl_config.get("user_roles", {})
        
        # Initialize rate limiter if Redis is available
        self.rate_limiter = None
        if redis_client and acl_config.get("rate_limiting", {}).get("enabled", True):
            key_prefix = acl_config.get("rate_limiting", {}).get("key_prefix", "mcp_rate_limit")
            self.rate_limiter = RateLimiter(redis_client, key_prefix)
    
    def get_user_role(self, api_key: Optional[str] = None, user_id: Optional[str] = None) -> str:
        """Get the role for a user based on API key or user ID."""
        if api_key and api_key in self.api_key_roles:
            return self.api_key_roles[api_key]
        
        if user_id and user_id in self.user_roles:
            return self.user_roles[user_id]
        
        return self.default_role
    
    def get_role_permissions(self, role: str) -> Dict[str, Any]:
        """Get permissions for a specific role."""
        if role not in self.roles:
            logger.warning(f"Role '{role}' not found, using default role '{self.default_role}'")
            role = self.default_role
        
        return self.roles.get(role, {})
    
    def check_server_access(self, role: str, server_id: str) -> bool:
        """Check if a role has access to a server."""
        role_perms = self.get_role_permissions(role)
        permissions = role_perms.get("permissions", {})
        
        return server_id in permissions
    
    def check_resource_access(
        self, 
        role: str, 
        server_id: str, 
        resource_name: str
    ) -> bool:
        """Check if a role has access to a specific resource."""
        role_perms = self.get_role_permissions(role)
        permissions = role_perms.get("permissions", {})
        
        if server_id not in permissions:
            return False
        
        server_perms = permissions[server_id]
        allowed_resources = server_perms.get("resources", [])
        
        # Check for wildcard permission
        if "*" in allowed_resources:
            return True
        
        return resource_name in allowed_resources
    
    def check_tool_access(
        self, 
        role: str, 
        server_id: str, 
        tool_name: str
    ) -> bool:
        """Check if a role has access to a specific tool."""
        role_perms = self.get_role_permissions(role)
        permissions = role_perms.get("permissions", {})
        
        if server_id not in permissions:
            return False
        
        server_perms = permissions[server_id]
        allowed_tools = server_perms.get("tools", [])
        
        # Check for wildcard permission
        if "*" in allowed_tools:
            return True
        
        return tool_name in allowed_tools
    
    def check_operation_access(
        self, 
        role: str, 
        server_id: str, 
        operation: str
    ) -> bool:
        """
        Check if a role has access to a specific operation.
        
        Operations: read, write, delete
        """
        role_perms = self.get_role_permissions(role)
        permissions = role_perms.get("permissions", {})
        
        if server_id not in permissions:
            return False
        
        server_perms = permissions[server_id]
        allowed_operations = server_perms.get("operations", [])
        
        return operation in allowed_operations
    
    def check_rate_limit(
        self, 
        role: str, 
        identifier: str
    ) -> tuple[bool, Optional[str]]:
        """
        Check if request is within rate limits for the role.
        
        Returns:
            (allowed, reason) tuple
        """
        if not self.rate_limiter:
            return True, None
        
        role_perms = self.get_role_permissions(role)
        rate_limits = role_perms.get("rate_limits", {})
        
        limit_per_minute = rate_limits.get("requests_per_minute", 60)
        limit_per_hour = rate_limits.get("requests_per_hour", 1000)
        
        return self.rate_limiter.check_rate_limit(
            identifier, 
            limit_per_minute, 
            limit_per_hour
        )
    
    def validate_request(
        self,
        role: str,
        server_id: str,
        operation_type: str,  # "resource", "tool", "prompt"
        operation_name: str,
        operation: str = "read",  # "read", "write", "delete"
        identifier: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Validate a complete MCP request.
        
        Returns:
            (allowed, reason) tuple
        """
        # Check server access
        if not self.check_server_access(role, server_id):
            return False, f"Role '{role}' does not have access to server '{server_id}'"
        
        # Check operation access
        if not self.check_operation_access(role, server_id, operation):
            return False, f"Role '{role}' does not have '{operation}' permission for server '{server_id}'"
        
        # Check specific resource/tool access
        if operation_type == "resource":
            if not self.check_resource_access(role, server_id, operation_name):
                return False, f"Role '{role}' does not have access to resource '{operation_name}'"
        elif operation_type == "tool":
            if not self.check_tool_access(role, server_id, operation_name):
                return False, f"Role '{role}' does not have access to tool '{operation_name}'"
        
        # Check rate limits
        if identifier:
            allowed, reason = self.check_rate_limit(role, identifier)
            if not allowed:
                return False, reason
        
        return True, None
    
    def get_available_servers(self, role: str) -> List[str]:
        """Get list of servers accessible to a role."""
        role_perms = self.get_role_permissions(role)
        permissions = role_perms.get("permissions", {})
        return list(permissions.keys())
    
    def get_available_tools(self, role: str, server_id: str) -> List[str]:
        """Get list of tools accessible to a role for a specific server."""
        role_perms = self.get_role_permissions(role)
        permissions = role_perms.get("permissions", {})
        
        if server_id not in permissions:
            return []
        
        server_perms = permissions[server_id]
        allowed_tools = server_perms.get("tools", [])
        
        return allowed_tools
    
    def get_available_resources(self, role: str, server_id: str) -> List[str]:
        """Get list of resources accessible to a role for a specific server."""
        role_perms = self.get_role_permissions(role)
        permissions = role_perms.get("permissions", {})
        
        if server_id not in permissions:
            return []
        
        server_perms = permissions[server_id]
        allowed_resources = server_perms.get("resources", [])
        
        return allowed_resources
    
    def get_role_summary(self, role: str) -> Dict[str, Any]:
        """Get a summary of role permissions."""
        role_perms = self.get_role_permissions(role)
        
        return {
            "role": role,
            "description": role_perms.get("description", ""),
            "servers": list(role_perms.get("permissions", {}).keys()),
            "rate_limits": role_perms.get("rate_limits", {}),
            "permissions": {
                server_id: {
                    "operations": perms.get("operations", []),
                    "resources_count": len(perms.get("resources", [])),
                    "tools_count": len(perms.get("tools", []))
                }
                for server_id, perms in role_perms.get("permissions", {}).items()
            }
        }
