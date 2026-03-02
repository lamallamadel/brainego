#!/usr/bin/env python3
"""
MCP Client Service for MCPJungle Gateway.

Provides client interface to MCP servers with:
- Server lifecycle management
- Request/response handling
- Connection pooling
- Error handling and retries
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import subprocess

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from safety_sanitizer import redact_secrets

logger = logging.getLogger(__name__)


class MCPServerConnection:
    """Represents a connection to an MCP server."""
    
    def __init__(self, server_id: str, config: Dict[str, Any]):
        self.server_id = server_id
        self.config = config
        self.session: Optional[ClientSession] = None
        self.read = None
        self.write = None
        self.connected = False
        self.last_error = None
        self.connection_count = 0
        
    async def connect(self):
        """Establish connection to MCP server."""
        if self.connected:
            return
            
        try:
            logger.info(f"Connecting to MCP server: {self.server_id}")
            
            # Prepare server parameters
            server_params = StdioServerParameters(
                command=self.config["command"],
                args=self.config.get("args", []),
                env=self.config.get("env", {})
            )
            
            # Create stdio client
            self.read, self.write = await stdio_client(server_params)
            
            # Create session
            self.session = ClientSession(self.read, self.write)
            await self.session.__aenter__()
            
            self.connected = True
            self.connection_count += 1
            self.last_error = None
            
            logger.info(
                f"Successfully connected to {self.server_id} "
                f"(connection #{self.connection_count})"
            )
            
        except Exception as e:
            self.last_error = str(e)
            self.connected = False
            logger.error(f"Failed to connect to {self.server_id}: {e}")
            raise
    
    async def disconnect(self):
        """Close connection to MCP server."""
        if not self.connected:
            return
            
        try:
            if self.session:
                await self.session.__aexit__(None, None, None)
            self.session = None
            self.read = None
            self.write = None
            self.connected = False
            logger.info(f"Disconnected from {self.server_id}")
        except Exception as e:
            logger.error(f"Error disconnecting from {self.server_id}: {e}")
    
    async def list_resources(self) -> List[Dict[str, Any]]:
        """List available resources from the server."""
        if not self.connected or not self.session:
            await self.connect()
        
        try:
            resources = await self.session.list_resources()
            return [
                {
                    "uri": r.uri,
                    "name": r.name,
                    "description": r.description,
                    "mimeType": r.mimeType
                }
                for r in resources.resources
            ]
        except Exception as e:
            logger.error(f"Error listing resources from {self.server_id}: {e}")
            raise
    
    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a specific resource."""
        if not self.connected or not self.session:
            await self.connect()
        
        try:
            result = await self.session.read_resource(uri)
            return {
                "uri": result.uri,
                "contents": [
                    {
                        "uri": c.uri,
                        "mimeType": c.mimeType,
                        "text": c.text if hasattr(c, "text") else None,
                        "blob": c.blob if hasattr(c, "blob") else None
                    }
                    for c in result.contents
                ]
            }
        except Exception as e:
            logger.error(f"Error reading resource {uri} from {self.server_id}: {e}")
            raise
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the server."""
        if not self.connected or not self.session:
            await self.connect()
        
        try:
            tools = await self.session.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema
                }
                for t in tools.tools
            ]
        except Exception as e:
            logger.error(f"Error listing tools from {self.server_id}: {e}")
            raise
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the server."""
        if not self.connected or not self.session:
            await self.connect()
        
        safe_arguments_payload, argument_redactions = redact_secrets({"arguments": arguments or {}})
        safe_arguments = safe_arguments_payload.get("arguments", {})

        try:
            logger.info(
                "Calling tool on %s: tool=%s argument_redactions=%s arguments=%s",
                self.server_id,
                tool_name,
                argument_redactions,
                safe_arguments,
            )
            result = await self.session.call_tool(tool_name, arguments)
            payload = {
                "content": [
                    {
                        "type": c.type,
                        "text": c.text if hasattr(c, "text") else None,
                        "data": c.data if hasattr(c, "data") else None
                    }
                    for c in result.content
                ],
                "isError": result.isError if hasattr(result, "isError") else False
            }
            _, output_redactions = redact_secrets(payload)
            if output_redactions:
                logger.warning(
                    "Tool result redacted in logs for %s.%s output_redactions=%s",
                    self.server_id,
                    tool_name,
                    output_redactions,
                )
            return payload
        except Exception as e:
            safe_error, error_redactions = redact_secrets(str(e))
            logger.error(
                "Error calling tool %s on %s: error=%s argument_redactions=%s error_redactions=%s",
                tool_name,
                self.server_id,
                safe_error,
                argument_redactions,
                error_redactions,
            )
            raise
    
    async def list_prompts(self) -> List[Dict[str, Any]]:
        """List available prompts from the server."""
        if not self.connected or not self.session:
            await self.connect()
        
        try:
            prompts = await self.session.list_prompts()
            return [
                {
                    "name": p.name,
                    "description": p.description,
                    "arguments": [
                        {
                            "name": arg.name,
                            "description": arg.description,
                            "required": arg.required
                        }
                        for arg in (p.arguments or [])
                    ]
                }
                for p in prompts.prompts
            ]
        except Exception as e:
            logger.error(f"Error listing prompts from {self.server_id}: {e}")
            raise
    
    async def get_prompt(self, prompt_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get a prompt from the server."""
        if not self.connected or not self.session:
            await self.connect()
        
        try:
            result = await self.session.get_prompt(prompt_name, arguments)
            return {
                "description": result.description,
                "messages": [
                    {
                        "role": m.role,
                        "content": {
                            "type": m.content.type,
                            "text": m.content.text if hasattr(m.content, "text") else None
                        }
                    }
                    for m in result.messages
                ]
            }
        except Exception as e:
            logger.error(f"Error getting prompt {prompt_name} from {self.server_id}: {e}")
            raise


class MCPClientService:
    """Manages connections to multiple MCP servers."""
    
    def __init__(self, servers_config: Dict[str, Any]):
        self.servers_config = servers_config
        self.connections: Dict[str, MCPServerConnection] = {}
        self.lock = asyncio.Lock()
        
    async def initialize(self):
        """Initialize connections to enabled MCP servers."""
        logger.info("Initializing MCP client service...")
        
        for server_id, config in self.servers_config.items():
            if not config.get("enabled", True):
                logger.info(f"Skipping disabled server: {server_id}")
                continue
            
            try:
                connection = MCPServerConnection(server_id, config)
                self.connections[server_id] = connection
                logger.info(f"Registered MCP server: {server_id}")
            except Exception as e:
                logger.error(f"Failed to register {server_id}: {e}")
        
        logger.info(f"Initialized {len(self.connections)} MCP server connections")
    
    async def get_connection(self, server_id: str) -> MCPServerConnection:
        """Get or create connection to a server."""
        if server_id not in self.connections:
            raise ValueError(f"Unknown MCP server: {server_id}")
        
        connection = self.connections[server_id]
        
        # Ensure connection is established
        if not connection.connected:
            async with self.lock:
                if not connection.connected:
                    await connection.connect()
        
        return connection
    
    async def list_servers(self) -> List[Dict[str, Any]]:
        """List all registered MCP servers."""
        servers = []
        for server_id, connection in self.connections.items():
            config = self.servers_config[server_id]
            servers.append({
                "id": server_id,
                "name": config.get("name", server_id),
                "description": config.get("description", ""),
                "type": config.get("type", "stdio"),
                "connected": connection.connected,
                "capabilities": config.get("capabilities", []),
                "enabled": config.get("enabled", True),
                "connection_count": connection.connection_count,
                "last_error": connection.last_error
            })
        return servers
    
    async def list_resources(self, server_id: str) -> List[Dict[str, Any]]:
        """List resources from a specific server."""
        connection = await self.get_connection(server_id)
        return await connection.list_resources()
    
    async def read_resource(self, server_id: str, uri: str) -> Dict[str, Any]:
        """Read a resource from a specific server."""
        connection = await self.get_connection(server_id)
        return await connection.read_resource(uri)
    
    async def list_tools(self, server_id: str) -> List[Dict[str, Any]]:
        """List tools from a specific server."""
        connection = await self.get_connection(server_id)
        return await connection.list_tools()
    
    async def call_tool(
        self, 
        server_id: str, 
        tool_name: str, 
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call a tool on a specific server."""
        connection = await self.get_connection(server_id)
        return await connection.call_tool(tool_name, arguments)
    
    async def list_prompts(self, server_id: str) -> List[Dict[str, Any]]:
        """List prompts from a specific server."""
        connection = await self.get_connection(server_id)
        return await connection.list_prompts()
    
    async def get_prompt(
        self, 
        server_id: str, 
        prompt_name: str, 
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get a prompt from a specific server."""
        connection = await self.get_connection(server_id)
        return await connection.get_prompt(prompt_name, arguments)
    
    async def close_all(self):
        """Close all server connections."""
        logger.info("Closing all MCP server connections...")
        for connection in self.connections.values():
            try:
                await connection.disconnect()
            except Exception as e:
                logger.error(f"Error closing connection to {connection.server_id}: {e}")
        logger.info("All MCP server connections closed")
