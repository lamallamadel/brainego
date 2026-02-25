#!/usr/bin/env python3
"""
Generate JWT tokens for Kong Gateway authentication (RS256 algorithm)
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

try:
    import jwt
except ImportError:
    print("Error: PyJWT library not found")
    print("Install with: pip install pyjwt cryptography")
    sys.exit(1)


def generate_jwt(
    private_key_path: str,
    key_id: str = "admin-key",
    subject: str = "test-user",
    audience: str = "ai-platform",
    scopes: list = None,
    expiration_hours: int = 1,
    additional_claims: dict = None
) -> str:
    """
    Generate a JWT token signed with RS256 algorithm.
    
    Args:
        private_key_path: Path to RSA private key file
        key_id: Key ID (kid claim)
        subject: Subject (sub claim) - usually user ID
        audience: Audience (aud claim)
        scopes: List of scopes/permissions
        expiration_hours: Token expiration time in hours
        additional_claims: Additional custom claims
    
    Returns:
        Encoded JWT token string
    """
    # Read private key
    with open(private_key_path, 'r') as f:
        private_key = f.read()
    
    # Set default scopes
    if scopes is None:
        scopes = ['api.read', 'api.write']
    
    # Create token payload
    now = datetime.datetime.utcnow()
    payload = {
        'iss': key_id,  # Issuer (must match Kong JWT credential key)
        'sub': subject,  # Subject (user identifier)
        'aud': audience,  # Audience
        'exp': now + datetime.timedelta(hours=expiration_hours),  # Expiration
        'nbf': now,  # Not before
        'iat': now,  # Issued at
        'kid': key_id,  # Key ID
        'scopes': scopes,  # Scopes/permissions
    }
    
    # Add additional claims if provided
    if additional_claims:
        payload.update(additional_claims)
    
    # Sign token with RS256
    token = jwt.encode(payload, private_key, algorithm='RS256')
    
    return token


def decode_jwt(token: str, public_key_path: str = None, verify: bool = False) -> dict:
    """
    Decode and optionally verify a JWT token.
    
    Args:
        token: JWT token string
        public_key_path: Path to RSA public key file (required if verify=True)
        verify: Whether to verify the signature
    
    Returns:
        Decoded token payload
    """
    if verify and not public_key_path:
        raise ValueError("public_key_path required when verify=True")
    
    if verify:
        with open(public_key_path, 'r') as f:
            public_key = f.read()
        decoded = jwt.decode(token, public_key, algorithms=['RS256'])
    else:
        decoded = jwt.decode(token, options={"verify_signature": False})
    
    return decoded


def main():
    parser = argparse.ArgumentParser(
        description='Generate JWT tokens for Kong Gateway authentication',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate token with default settings
  %(prog)s --private-key kong-jwt-keys/kong-jwt-private.pem
  
  # Generate token with custom expiration and scopes
  %(prog)s --private-key kong-jwt-keys/kong-jwt-private.pem \\
    --expiration 24 --scopes api.read api.write admin
  
  # Generate token with custom claims
  %(prog)s --private-key kong-jwt-keys/kong-jwt-private.pem \\
    --subject user-123 --claims workspace_id:workspace-456
  
  # Decode and verify token
  %(prog)s --decode <token> --public-key kong-jwt-keys/kong-jwt-public.pem --verify
"""
    )
    
    parser.add_argument(
        '--private-key',
        type=str,
        help='Path to RSA private key file'
    )
    parser.add_argument(
        '--public-key',
        type=str,
        help='Path to RSA public key file (for verification)'
    )
    parser.add_argument(
        '--key-id',
        type=str,
        default='admin-key',
        help='Key ID (kid claim) - default: admin-key'
    )
    parser.add_argument(
        '--subject',
        type=str,
        default='test-user',
        help='Subject (sub claim) - usually user ID - default: test-user'
    )
    parser.add_argument(
        '--audience',
        type=str,
        default='ai-platform',
        help='Audience (aud claim) - default: ai-platform'
    )
    parser.add_argument(
        '--scopes',
        nargs='+',
        default=['api.read', 'api.write'],
        help='Scopes/permissions - default: api.read api.write'
    )
    parser.add_argument(
        '--expiration',
        type=int,
        default=1,
        help='Token expiration time in hours - default: 1'
    )
    parser.add_argument(
        '--claims',
        nargs='+',
        help='Additional claims in key:value format'
    )
    parser.add_argument(
        '--decode',
        type=str,
        help='Decode existing JWT token'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify token signature when decoding'
    )
    parser.add_argument(
        '--output',
        choices=['token', 'json', 'curl'],
        default='token',
        help='Output format - default: token'
    )
    
    args = parser.parse_args()
    
    # Decode mode
    if args.decode:
        try:
            decoded = decode_jwt(
                args.decode,
                public_key_path=args.public_key,
                verify=args.verify
            )
            print(json.dumps(decoded, indent=2))
            
            # Check expiration
            exp = decoded.get('exp')
            if exp:
                exp_dt = datetime.datetime.fromtimestamp(exp)
                now = datetime.datetime.utcnow()
                if exp_dt < now:
                    print("\n⚠ Token is EXPIRED", file=sys.stderr)
                else:
                    remaining = exp_dt - now
                    print(f"\n✓ Token valid for {remaining}", file=sys.stderr)
        except jwt.ExpiredSignatureError:
            print("Error: Token has expired", file=sys.stderr)
            sys.exit(1)
        except jwt.InvalidSignatureError:
            print("Error: Invalid token signature", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error decoding token: {e}", file=sys.stderr)
            sys.exit(1)
        return
    
    # Generate mode
    if not args.private_key:
        parser.error("--private-key required for token generation")
    
    if not Path(args.private_key).exists():
        print(f"Error: Private key file not found: {args.private_key}", file=sys.stderr)
        sys.exit(1)
    
    # Parse additional claims
    additional_claims = {}
    if args.claims:
        for claim in args.claims:
            if ':' not in claim:
                print(f"Error: Invalid claim format '{claim}' (use key:value)", file=sys.stderr)
                sys.exit(1)
            key, value = claim.split(':', 1)
            additional_claims[key] = value
    
    # Generate token
    try:
        token = generate_jwt(
            private_key_path=args.private_key,
            key_id=args.key_id,
            subject=args.subject,
            audience=args.audience,
            scopes=args.scopes,
            expiration_hours=args.expiration,
            additional_claims=additional_claims
        )
        
        # Output based on format
        if args.output == 'token':
            print(token)
        elif args.output == 'json':
            output = {
                'token': token,
                'expires_in': args.expiration * 3600,
                'token_type': 'Bearer',
                'scope': ' '.join(args.scopes)
            }
            print(json.dumps(output, indent=2))
        elif args.output == 'curl':
            print(f'export JWT_TOKEN="{token}"')
            print(f'curl -H "Authorization: Bearer $JWT_TOKEN" https://api.your-domain.com/v1/chat/completions')
    except Exception as e:
        print(f"Error generating token: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
