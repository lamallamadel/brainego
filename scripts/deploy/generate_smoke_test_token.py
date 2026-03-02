#!/usr/bin/env python3
"""
Generate Authentication Token for Smoke Tests

Creates a JWT token for use with production smoke tests.
Supports both RS256 (Kong JWT) and HS256 (simple JWT) signing.
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Needs: python-package:pyjwt>=2.8.0
# Needs: python-package:cryptography>=41.0.0
try:
    import jwt
except ImportError:
    print("Error: pyjwt not available")
    print("Add to requirements-deploy.txt: pyjwt>=2.8.0 cryptography>=41.0.0")
    sys.exit(1)


def generate_jwt_rs256(
    subject: str,
    key_id: str,
    private_key_path: str,
    workspace_id: str,
    expiration_hours: int = 24,
    scopes: list = None
) -> str:
    """Generate JWT token with RS256 signing (Kong JWT plugin)"""
    
    if scopes is None:
        scopes = ['api.read', 'api.write']
    
    # Load private key
    private_key_file = Path(private_key_path)
    if not private_key_file.exists():
        raise FileNotFoundError(f"Private key not found: {private_key_path}")
    
    with open(private_key_file, 'r') as f:
        private_key = f.read()
    
    # Build JWT payload
    now = time.time()
    payload = {
        'iss': key_id,
        'sub': subject,
        'aud': 'ai-platform',
        'exp': int(now + expiration_hours * 3600),
        'nbf': int(now),
        'iat': int(now),
        'kid': key_id,
        'scopes': scopes,
        'workspace_id': workspace_id
    }
    
    # Sign token
    token = jwt.encode(payload, private_key, algorithm='RS256')
    
    return token


def generate_jwt_hs256(
    subject: str,
    secret: str,
    workspace_id: str,
    expiration_hours: int = 24,
    scopes: list = None
) -> str:
    """Generate JWT token with HS256 signing (simple JWT)"""
    
    if scopes is None:
        scopes = ['api.read', 'api.write']
    
    # Build JWT payload
    now = time.time()
    payload = {
        'sub': subject,
        'aud': 'ai-platform',
        'exp': int(now + expiration_hours * 3600),
        'nbf': int(now),
        'iat': int(now),
        'scopes': scopes,
        'workspace_id': workspace_id
    }
    
    # Sign token
    token = jwt.encode(payload, secret, algorithm='HS256')
    
    return token


def decode_and_verify(token: str, verify: bool = False) -> dict:
    """Decode JWT token without verification (for inspection)"""
    
    try:
        # Decode without verification (just for display)
        decoded = jwt.decode(token, options={"verify_signature": False})
        return decoded
    except Exception as e:
        raise ValueError(f"Failed to decode token: {e}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Generate authentication token for production smoke tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate Kong JWT (RS256) token
  python generate_smoke_test_token.py \\
    --method rs256 \\
    --private-key kong-jwt-keys/kong-jwt-private.pem \\
    --key-id admin-key \\
    --subject test-user \\
    --workspace-id prod-workspace

  # Generate simple JWT (HS256) token
  python generate_smoke_test_token.py \\
    --method hs256 \\
    --secret your-secret-key \\
    --subject test-user \\
    --workspace-id prod-workspace

  # Generate token with custom expiration and scopes
  python generate_smoke_test_token.py \\
    --method rs256 \\
    --private-key kong-jwt-keys/kong-jwt-private.pem \\
    --key-id admin-key \\
    --subject test-user \\
    --workspace-id prod-workspace \\
    --expiration-hours 1 \\
    --scopes api.read api.write mcp.call

  # Use token in smoke tests
  export AUTH_TOKEN=$(python generate_smoke_test_token.py --method rs256 ...)
  python prod_smoke_tests.py --base-url https://api.example.com --workspace-id prod-workspace
        """
    )
    
    # Method selection
    parser.add_argument(
        "--method",
        choices=['rs256', 'hs256'],
        default='rs256',
        help="JWT signing method (default: rs256)"
    )
    
    # Common arguments
    parser.add_argument(
        "--subject",
        default="smoke-test-user",
        help="Subject (user ID) for JWT (default: smoke-test-user)"
    )
    parser.add_argument(
        "--workspace-id",
        required=True,
        help="Workspace ID for token"
    )
    parser.add_argument(
        "--expiration-hours",
        type=int,
        default=24,
        help="Token expiration in hours (default: 24)"
    )
    parser.add_argument(
        "--scopes",
        nargs="+",
        default=['api.read', 'api.write'],
        help="Token scopes (default: api.read api.write)"
    )
    
    # RS256-specific arguments
    parser.add_argument(
        "--private-key",
        help="Path to private key (for RS256)"
    )
    parser.add_argument(
        "--key-id",
        default="admin-key",
        help="Key ID (for RS256, default: admin-key)"
    )
    
    # HS256-specific arguments
    parser.add_argument(
        "--secret",
        help="Secret key (for HS256)"
    )
    
    # Output options
    parser.add_argument(
        "--output",
        choices=['token', 'json', 'env'],
        default='token',
        help="Output format: token (raw), json (pretty), or env (export statement)"
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Decode and display token contents (without verification)"
    )
    
    args = parser.parse_args()
    
    # Validate method-specific arguments
    if args.method == 'rs256':
        if not args.private_key:
            parser.error("--private-key required for RS256 method")
        
        try:
            token = generate_jwt_rs256(
                subject=args.subject,
                key_id=args.key_id,
                private_key_path=args.private_key,
                workspace_id=args.workspace_id,
                expiration_hours=args.expiration_hours,
                scopes=args.scopes
            )
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            print("", file=sys.stderr)
            print("To generate Kong JWT keys:", file=sys.stderr)
            print("  mkdir -p kong-jwt-keys", file=sys.stderr)
            print("  openssl genrsa -out kong-jwt-keys/kong-jwt-private.pem 2048", file=sys.stderr)
            print("  openssl rsa -in kong-jwt-keys/kong-jwt-private.pem -pubout -out kong-jwt-keys/kong-jwt-public.pem", file=sys.stderr)
            sys.exit(1)
    
    elif args.method == 'hs256':
        if not args.secret:
            parser.error("--secret required for HS256 method")
        
        token = generate_jwt_hs256(
            subject=args.subject,
            secret=args.secret,
            workspace_id=args.workspace_id,
            expiration_hours=args.expiration_hours,
            scopes=args.scopes
        )
    
    # Output token
    if args.output == 'token':
        print(token)
    
    elif args.output == 'json':
        decoded = decode_and_verify(token)
        print(json.dumps({
            'token': token,
            'decoded': decoded
        }, indent=2))
    
    elif args.output == 'env':
        print(f"export AUTH_TOKEN='{token}'")
    
    # Inspect if requested
    if args.inspect:
        print("", file=sys.stderr)
        print("Token payload:", file=sys.stderr)
        decoded = decode_and_verify(token)
        print(json.dumps(decoded, indent=2), file=sys.stderr)
        print("", file=sys.stderr)
        
        # Calculate expiration time
        exp_timestamp = decoded.get('exp', 0)
        import datetime
        exp_datetime = datetime.datetime.fromtimestamp(exp_timestamp)
        print(f"Expires: {exp_datetime.isoformat()}", file=sys.stderr)


if __name__ == "__main__":
    main()
