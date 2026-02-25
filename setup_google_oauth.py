#!/usr/bin/env python3
"""
Helper script to set up Google OAuth 2.0 credentials for Gmail and Calendar MCP servers.

This script helps users obtain OAuth 2.0 refresh tokens needed for:
- Gmail MCP Server (read-only access)
- Google Calendar MCP Server

Usage:
    python setup_google_oauth.py --service gmail
    python setup_google_oauth.py --service calendar
"""

import argparse
import json
import webbrowser
from urllib.parse import urlencode
import http.server
import socketserver
from urllib.parse import parse_qs, urlparse

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]

CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly"
]

REDIRECT_URI = "http://localhost:8080"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class OAuthCallbackHandler(http.server.SimpleHTTPRequestHandler):
    """Handle OAuth callback."""
    
    authorization_code = None
    
    def do_GET(self):
        """Handle GET request with authorization code."""
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if 'code' in params:
            OAuthCallbackHandler.authorization_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = """
            <html>
            <body>
                <h1>Authorization Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = """
            <html>
            <body>
                <h1>Authorization Failed</h1>
                <p>No authorization code received.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
    
    def log_message(self, format, *args):
        """Suppress log messages."""
        pass


def get_authorization_url(client_id: str, scopes: list, state: str = "state") -> str:
    """Generate OAuth authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "state": state,
        "prompt": "consent"
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


def exchange_code_for_tokens(
    client_id: str,
    client_secret: str,
    authorization_code: str
) -> dict:
    """Exchange authorization code for access and refresh tokens."""
    import urllib.request
    
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": authorization_code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    
    request = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise Exception(f"Token exchange failed: {error_body}")


def setup_oauth(service: str):
    """Set up OAuth for a service."""
    print(f"\n{'=' * 70}")
    print(f"Google OAuth 2.0 Setup for {service.upper()}".center(70))
    print(f"{'=' * 70}\n")
    
    if service == "gmail":
        scopes = GMAIL_SCOPES
        print("This will set up OAuth for Gmail (read-only access)")
    elif service == "calendar":
        scopes = CALENDAR_SCOPES
        print("This will set up OAuth for Google Calendar")
    else:
        print(f"Unknown service: {service}")
        return
    
    print("\nRequired scopes:")
    for scope in scopes:
        print(f"  - {scope}")
    
    print("\n" + "=" * 70)
    print("PREREQUISITES".center(70))
    print("=" * 70)
    print("""
1. Go to Google Cloud Console: https://console.cloud.google.com/
2. Create a new project or select an existing one
3. Enable the required API:
   - For Gmail: Enable "Gmail API"
   - For Calendar: Enable "Google Calendar API"
4. Go to "APIs & Services" > "Credentials"
5. Create OAuth 2.0 Client ID:
   - Application type: Desktop app
   - Name: MCP Server (or any name)
6. Download the credentials JSON or copy Client ID and Secret
""")
    
    input("\nPress Enter when you have completed the prerequisites...")
    
    print("\n" + "=" * 70)
    print("ENTER CLIENT CREDENTIALS".center(70))
    print("=" * 70)
    
    client_id = input("\nEnter your Client ID: ").strip()
    client_secret = input("Enter your Client Secret: ").strip()
    
    if not client_id or not client_secret:
        print("\nError: Client ID and Secret are required")
        return
    
    auth_url = get_authorization_url(client_id, scopes)
    
    print("\n" + "=" * 70)
    print("AUTHORIZATION".center(70))
    print("=" * 70)
    print("\nOpening browser for authorization...")
    print(f"\nIf the browser doesn't open, visit this URL:\n{auth_url}")
    
    print(f"\nStarting local server on {REDIRECT_URI}...")
    print("Waiting for authorization...")
    
    try:
        webbrowser.open(auth_url)
    except Exception as e:
        print(f"Could not open browser: {e}")
    
    with socketserver.TCPServer(("", 8080), OAuthCallbackHandler) as httpd:
        httpd.handle_request()
    
    if not OAuthCallbackHandler.authorization_code:
        print("\nError: No authorization code received")
        return
    
    print("\nAuthorization code received!")
    print("\nExchanging authorization code for tokens...")
    
    try:
        tokens = exchange_code_for_tokens(
            client_id,
            client_secret,
            OAuthCallbackHandler.authorization_code
        )
    except Exception as e:
        print(f"\nError exchanging code: {e}")
        return
    
    print("\n" + "=" * 70)
    print("SUCCESS!".center(70))
    print("=" * 70)
    
    print(f"\nAdd these to your .env.mcpjungle file:\n")
    
    if service == "gmail":
        print(f"GMAIL_CLIENT_ID={client_id}")
        print(f"GMAIL_CLIENT_SECRET={client_secret}")
        print(f"GMAIL_REFRESH_TOKEN={tokens.get('refresh_token', 'NOT_RECEIVED')}")
    elif service == "calendar":
        print(f"GOOGLE_CALENDAR_CLIENT_ID={client_id}")
        print(f"GOOGLE_CALENDAR_CLIENT_SECRET={client_secret}")
        print(f"GOOGLE_CALENDAR_REFRESH_TOKEN={tokens.get('refresh_token', 'NOT_RECEIVED')}")
    
    print("\n" + "=" * 70)
    print("IMPORTANT NOTES".center(70))
    print("=" * 70)
    print("""
1. Keep your Client Secret and Refresh Token secure
2. Never commit these credentials to version control
3. The refresh token is long-lived and can be used to get new access tokens
4. If you don't see a refresh token, make sure you included 'access_type=offline'
   and 'prompt=consent' in the authorization URL
""")
    
    if not tokens.get('refresh_token'):
        print("\n⚠ WARNING: No refresh token received!")
        print("This might happen if you previously authorized this app.")
        print("To fix this:")
        print("1. Go to https://myaccount.google.com/permissions")
        print("2. Remove access for your app")
        print("3. Run this script again")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Set up Google OAuth 2.0 for MCP servers"
    )
    parser.add_argument(
        "--service",
        choices=["gmail", "calendar"],
        required=True,
        help="Service to set up OAuth for"
    )
    
    args = parser.parse_args()
    
    try:
        setup_oauth(args.service)
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
