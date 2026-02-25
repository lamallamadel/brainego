#!/usr/bin/env python3
"""
Kong Gateway Authentication Client Example
Demonstrates OAuth 2.1 and JWT authentication flows
"""

import os
import json
import time
import hashlib
import base64
import secrets
from typing import Optional, Dict, Any
from urllib.parse import urlencode, parse_qs

try:
    import httpx
    import jwt
except ImportError:
    print("Error: Required libraries not found")
    print("Install with: pip install httpx pyjwt cryptography")
    exit(1)


class KongAuthClient:
    """Client for Kong Gateway OAuth 2.1 and JWT authentication"""
    
    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        private_key_path: Optional[str] = None,
        public_key_path: Optional[str] = None
    ):
        """
        Initialize Kong authentication client.
        
        Args:
            base_url: Base URL of Kong Gateway (e.g., https://api.your-domain.com)
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            private_key_path: Path to JWT private key (for JWT auth)
            public_key_path: Path to JWT public key (for verification)
        """
        self.base_url = base_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.private_key_path = private_key_path
        self.public_key_path = public_key_path
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: Optional[float] = None
    
    # OAuth 2.1 with PKCE Methods
    
    def generate_pkce_pair(self) -> tuple[str, str]:
        """
        Generate PKCE code verifier and challenge.
        
        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate code verifier (43-128 characters)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        
        # Generate code challenge (SHA256 hash of verifier)
        challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    def get_authorization_url(
        self,
        redirect_uri: str,
        scopes: list[str] = None,
        state: str = None
    ) -> tuple[str, str, str]:
        """
        Generate OAuth2 authorization URL with PKCE.
        
        Args:
            redirect_uri: OAuth2 redirect URI
            scopes: List of requested scopes
            state: Optional state parameter for CSRF protection
        
        Returns:
            Tuple of (authorization_url, code_verifier, state)
        """
        if scopes is None:
            scopes = ['api.read', 'api.write']
        
        if state is None:
            state = secrets.token_urlsafe(32)
        
        code_verifier, code_challenge = self.generate_pkce_pair()
        
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'scope': ' '.join(scopes),
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }
        
        auth_url = f"{self.base_url}/oauth2/authorize?{urlencode(params)}"
        return auth_url, code_verifier, state
    
    async def exchange_authorization_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from callback
            redirect_uri: OAuth2 redirect URI (must match authorization request)
            code_verifier: PKCE code verifier
        
        Returns:
            Token response containing access_token, refresh_token, etc.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/oauth2/token",
                data={
                    'grant_type': 'authorization_code',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'code': code,
                    'redirect_uri': redirect_uri,
                    'code_verifier': code_verifier
                }
            )
            response.raise_for_status()
            token_data = response.json()
            
            # Store tokens
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token')
            if 'expires_in' in token_data:
                self.token_expiry = time.time() + token_data['expires_in']
            
            return token_data
    
    async def exchange_client_credentials(self, scopes: list[str] = None) -> Dict[str, Any]:
        """
        Get access token using client credentials grant.
        
        Args:
            scopes: List of requested scopes
        
        Returns:
            Token response containing access_token
        """
        if scopes is None:
            scopes = ['api.read', 'api.write']
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/oauth2/token",
                data={
                    'grant_type': 'client_credentials',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'scope': ' '.join(scopes)
                }
            )
            response.raise_for_status()
            token_data = response.json()
            
            # Store tokens
            self.access_token = token_data.get('access_token')
            if 'expires_in' in token_data:
                self.token_expiry = time.time() + token_data['expires_in']
            
            return token_data
    
    async def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refresh access token using refresh token.
        
        Returns:
            Token response with new access_token
        """
        if not self.refresh_token:
            raise ValueError("No refresh token available")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/oauth2/token",
                data={
                    'grant_type': 'refresh_token',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'refresh_token': self.refresh_token
                }
            )
            response.raise_for_status()
            token_data = response.json()
            
            # Update tokens
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token', self.refresh_token)
            if 'expires_in' in token_data:
                self.token_expiry = time.time() + token_data['expires_in']
            
            return token_data
    
    def is_token_expired(self) -> bool:
        """Check if access token is expired."""
        if not self.token_expiry:
            return True
        return time.time() >= self.token_expiry
    
    # JWT Methods
    
    def generate_jwt(
        self,
        subject: str = "test-user",
        key_id: str = "admin-key",
        expiration_hours: int = 1,
        additional_claims: dict = None
    ) -> str:
        """
        Generate JWT token signed with RS256.
        
        Args:
            subject: Subject (user ID)
            key_id: Key ID (must match Kong JWT credential)
            expiration_hours: Token expiration in hours
            additional_claims: Additional custom claims
        
        Returns:
            Signed JWT token
        """
        if not self.private_key_path:
            raise ValueError("Private key path not configured")
        
        with open(self.private_key_path, 'r') as f:
            private_key = f.read()
        
        now = time.time()
        payload = {
            'iss': key_id,
            'sub': subject,
            'aud': 'ai-platform',
            'exp': int(now + expiration_hours * 3600),
            'nbf': int(now),
            'iat': int(now),
            'kid': key_id,
            'scopes': ['api.read', 'api.write']
        }
        
        if additional_claims:
            payload.update(additional_claims)
        
        token = jwt.encode(payload, private_key, algorithm='RS256')
        self.access_token = token
        self.token_expiry = payload['exp']
        
        return token
    
    # API Request Methods
    
    async def request(
        self,
        method: str,
        path: str,
        headers: dict = None,
        **kwargs
    ) -> httpx.Response:
        """
        Make authenticated API request.
        
        Args:
            method: HTTP method
            path: API path
            headers: Additional headers
            **kwargs: Additional httpx request parameters
        
        Returns:
            HTTP response
        """
        if not self.access_token:
            raise ValueError("No access token available. Authenticate first.")
        
        # Auto-refresh if expired
        if self.is_token_expired() and self.refresh_token:
            await self.refresh_access_token()
        
        if headers is None:
            headers = {}
        
        headers['Authorization'] = f'Bearer {self.access_token}'
        
        url = f"{self.base_url}{path}"
        
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=headers, **kwargs)
            return response
    
    async def chat_completion(
        self,
        messages: list[dict],
        model: str = "llama-3.3-8b-instruct",
        workspace_id: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make chat completion request.
        
        Args:
            messages: Chat messages
            model: Model name
            workspace_id: Optional workspace ID for token budget tracking
            **kwargs: Additional completion parameters
        
        Returns:
            Completion response
        """
        headers = {}
        if workspace_id:
            headers['X-Workspace-Id'] = workspace_id
        
        response = await self.request(
            'POST',
            '/v1/chat/completions',
            headers=headers,
            json={
                'model': model,
                'messages': messages,
                **kwargs
            }
        )
        response.raise_for_status()
        return response.json()


async def example_oauth2_client_credentials():
    """Example: OAuth2 Client Credentials Flow"""
    print("\n" + "="*60)
    print("OAuth2 Client Credentials Flow Example")
    print("="*60)
    
    client = KongAuthClient(
        base_url=os.getenv('KONG_URL', 'https://api.your-domain.com'),
        client_id=os.getenv('OAUTH2_CLIENT_ID', 'your-client-id'),
        client_secret=os.getenv('OAUTH2_CLIENT_SECRET', 'your-client-secret')
    )
    
    # Get access token
    print("\n1. Getting access token...")
    token_data = await client.exchange_client_credentials(scopes=['api.read', 'api.write'])
    print(f"✓ Access token obtained")
    print(f"  Token type: {token_data.get('token_type')}")
    print(f"  Expires in: {token_data.get('expires_in')} seconds")
    print(f"  Scope: {token_data.get('scope')}")
    
    # Make API request
    print("\n2. Making chat completion request...")
    result = await client.chat_completion(
        messages=[{"role": "user", "content": "Hello, how are you?"}],
        workspace_id="test-workspace"
    )
    print(f"✓ Request successful")
    print(f"  Response: {result['choices'][0]['message']['content'][:100]}...")


async def example_jwt_authentication():
    """Example: JWT Authentication"""
    print("\n" + "="*60)
    print("JWT Authentication Example")
    print("="*60)
    
    client = KongAuthClient(
        base_url=os.getenv('KONG_URL', 'https://api.your-domain.com'),
        client_id='',  # Not needed for JWT
        client_secret='',
        private_key_path='kong-jwt-keys/kong-jwt-private.pem'
    )
    
    # Generate JWT
    print("\n1. Generating JWT token...")
    token = client.generate_jwt(
        subject='user-123',
        key_id='admin-key',
        expiration_hours=1,
        additional_claims={'workspace_id': 'workspace-456'}
    )
    print(f"✓ JWT token generated")
    print(f"  Token: {token[:50]}...")
    
    # Make API request
    print("\n2. Making authenticated request...")
    result = await client.chat_completion(
        messages=[{"role": "user", "content": "What is the capital of France?"}],
        workspace_id="workspace-456"
    )
    print(f"✓ Request successful")
    print(f"  Response: {result['choices'][0]['message']['content']}")


async def example_rate_limiting():
    """Example: Testing Rate Limits"""
    print("\n" + "="*60)
    print("Rate Limiting Example")
    print("="*60)
    
    client = KongAuthClient(
        base_url=os.getenv('KONG_URL', 'https://api.your-domain.com'),
        client_id=os.getenv('OAUTH2_CLIENT_ID', 'your-client-id'),
        client_secret=os.getenv('OAUTH2_CLIENT_SECRET', 'your-client-secret')
    )
    
    await client.exchange_client_credentials()
    
    print("\n1. Sending multiple requests to test rate limit...")
    for i in range(5):
        response = await client.request('GET', '/health')
        
        # Check rate limit headers
        print(f"\nRequest {i+1}:")
        print(f"  Status: {response.status_code}")
        for header in ['X-RateLimit-Limit-Minute', 'X-RateLimit-Remaining-Minute']:
            if header in response.headers:
                print(f"  {header}: {response.headers[header]}")


async def main():
    """Run all examples"""
    import asyncio
    
    print("Kong Gateway Authentication Examples")
    print("====================================")
    print("\nMake sure to set environment variables:")
    print("  KONG_URL - Kong Gateway URL")
    print("  OAUTH2_CLIENT_ID - OAuth2 client ID")
    print("  OAUTH2_CLIENT_SECRET - OAuth2 client secret")
    
    try:
        # Run examples
        await example_oauth2_client_credentials()
        await example_jwt_authentication()
        await example_rate_limiting()
        
        print("\n" + "="*60)
        print("All examples completed successfully!")
        print("="*60)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
