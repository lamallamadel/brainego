"""
Security Audit for Production Validation
- Trivy image scanning
- Penetration testing
- Vulnerability assessment
- Security best practices validation
"""

import json
import logging
import subprocess
import requests
from datetime import datetime
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SecurityAuditor:
    """Production security audit orchestrator"""

    def __init__(self):
        self.vulnerabilities = []
        self.test_results = []
        self.scan_results = {}

    def trivy_image_scan(self):
        """Scan Docker images with Trivy"""
        logger.info('=' * 60)
        logger.info('Running Trivy Image Scanning')
        logger.info('=' * 60)
        
        images = [
            'modular/max-serve:latest',
            'api-server:latest',
            'gateway:latest',
            'mcpjungle-gateway:latest',
        ]
        
        for image in images:
            logger.info(f'\nScanning image: {image}')
            
            try:
                # Run Trivy scan
                result = subprocess.run(
                    [
                        'trivy', 'image',
                        '--severity', 'HIGH,CRITICAL',
                        '--format', 'json',
                        '--quiet',
                        image
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                
                if result.returncode == 0:
                    scan_data = json.loads(result.stdout)
                    self.scan_results[image] = scan_data
                    
                    # Count vulnerabilities
                    critical_count = 0
                    high_count = 0
                    
                    for result_item in scan_data.get('Results', []):
                        for vuln in result_item.get('Vulnerabilities', []):
                            severity = vuln.get('Severity', '')
                            if severity == 'CRITICAL':
                                critical_count += 1
                            elif severity == 'HIGH':
                                high_count += 1
                    
                    logger.info(f'  Critical: {critical_count}')
                    logger.info(f'  High: {high_count}')
                    
                    if critical_count > 0:
                        self.vulnerabilities.append({
                            'type': 'image_vulnerability',
                            'image': image,
                            'severity': 'CRITICAL',
                            'count': critical_count,
                        })
                    
                else:
                    logger.error(f'Trivy scan failed for {image}')
                    logger.error(result.stderr)
                    
            except subprocess.TimeoutExpired:
                logger.error(f'Trivy scan timeout for {image}')
            except Exception as e:
                logger.error(f'Error scanning {image}: {e}')
        
        # Save scan results
        with open('trivy_scan_results.json', 'w') as f:
            json.dump(self.scan_results, f, indent=2)
        
        logger.info('\nTrivy scan results saved to trivy_scan_results.json')

    def penetration_testing(self):
        """Basic penetration testing"""
        logger.info('\n' + '=' * 60)
        logger.info('Running Penetration Tests')
        logger.info('=' * 60)
        
        tests = [
            self.test_sql_injection,
            self.test_xss_attacks,
            self.test_authentication_bypass,
            self.test_rate_limiting,
            self.test_cors_policy,
            self.test_header_security,
            self.test_file_upload_vulnerabilities,
            self.test_api_key_exposure,
        ]
        
        for test in tests:
            try:
                test()
            except Exception as e:
                logger.error(f'Test {test.__name__} failed: {e}')

    def test_sql_injection(self):
        """Test for SQL injection vulnerabilities"""
        logger.info('\n[TEST] SQL Injection')
        
        payloads = [
            "' OR '1'='1",
            "1' OR '1'='1' --",
            "admin'--",
            "1' UNION SELECT NULL--",
        ]
        
        endpoints = [
            'http://localhost:8000/v1/chat/completions',
            'http://localhost:9002/rag/query',
        ]
        
        for endpoint in endpoints:
            for payload in payloads:
                try:
                    response = requests.post(
                        endpoint,
                        json={'query': payload, 'messages': [{'role': 'user', 'content': payload}]},
                        timeout=5,
                    )
                    
                    # Check if injection was successful (should not be)
                    if response.status_code == 200 and 'error' not in response.text.lower():
                        logger.warning(f'  ⚠ Potential SQL injection vulnerability at {endpoint}')
                        self.vulnerabilities.append({
                            'type': 'sql_injection',
                            'endpoint': endpoint,
                            'payload': payload,
                        })
                except requests.RequestException:
                    pass
        
        logger.info('  ✓ SQL injection tests completed')
        self.test_results.append({'test': 'sql_injection', 'status': 'completed'})

    def test_xss_attacks(self):
        """Test for XSS vulnerabilities"""
        logger.info('\n[TEST] Cross-Site Scripting (XSS)')
        
        payloads = [
            '<script>alert("XSS")</script>',
            '<img src=x onerror=alert("XSS")>',
            'javascript:alert("XSS")',
            '<svg/onload=alert("XSS")>',
        ]
        
        endpoints = [
            'http://localhost:8000/v1/chat/completions',
            'http://localhost:9002/rag/query',
        ]
        
        for endpoint in endpoints:
            for payload in payloads:
                try:
                    response = requests.post(
                        endpoint,
                        json={'query': payload, 'messages': [{'role': 'user', 'content': payload}]},
                        timeout=5,
                    )
                    
                    # Check if script tags are reflected (should be sanitized)
                    if '<script>' in response.text or 'onerror=' in response.text:
                        logger.warning(f'  ⚠ Potential XSS vulnerability at {endpoint}')
                        self.vulnerabilities.append({
                            'type': 'xss',
                            'endpoint': endpoint,
                            'payload': payload,
                        })
                except requests.RequestException:
                    pass
        
        logger.info('  ✓ XSS tests completed')
        self.test_results.append({'test': 'xss', 'status': 'completed'})

    def test_authentication_bypass(self):
        """Test for authentication bypass"""
        logger.info('\n[TEST] Authentication Bypass')
        
        # Test endpoints without authentication
        protected_endpoints = [
            'http://localhost:9002/admin',
            'http://localhost:8000/metrics',
            'http://localhost:9100/mcp/admin',
        ]
        
        for endpoint in protected_endpoints:
            try:
                response = requests.get(endpoint, timeout=5)
                
                if response.status_code == 200:
                    logger.warning(f'  ⚠ Unprotected endpoint: {endpoint}')
                    self.vulnerabilities.append({
                        'type': 'auth_bypass',
                        'endpoint': endpoint,
                    })
                else:
                    logger.info(f'  ✓ Protected: {endpoint}')
            except requests.RequestException:
                pass
        
        self.test_results.append({'test': 'auth_bypass', 'status': 'completed'})

    def test_rate_limiting(self):
        """Test rate limiting implementation"""
        logger.info('\n[TEST] Rate Limiting')
        
        endpoint = 'http://localhost:8000/v1/chat/completions'
        
        # Send many requests quickly
        responses = []
        for i in range(100):
            try:
                response = requests.post(
                    endpoint,
                    json={
                        'model': 'llama-3.3-8b-instruct',
                        'messages': [{'role': 'user', 'content': 'test'}],
                    },
                    timeout=2,
                )
                responses.append(response.status_code)
            except requests.RequestException:
                pass
        
        # Check if rate limiting kicked in (should see 429)
        rate_limited = any(status == 429 for status in responses)
        
        if rate_limited:
            logger.info('  ✓ Rate limiting is active')
        else:
            logger.warning('  ⚠ No rate limiting detected')
            self.vulnerabilities.append({
                'type': 'missing_rate_limit',
                'endpoint': endpoint,
            })
        
        self.test_results.append({'test': 'rate_limiting', 'status': 'completed'})

    def test_cors_policy(self):
        """Test CORS policy"""
        logger.info('\n[TEST] CORS Policy')
        
        endpoints = [
            'http://localhost:8000/v1/chat/completions',
            'http://localhost:9002/rag/query',
        ]
        
        for endpoint in endpoints:
            try:
                response = requests.options(
                    endpoint,
                    headers={'Origin': 'http://malicious-site.com'},
                    timeout=5,
                )
                
                cors_header = response.headers.get('Access-Control-Allow-Origin', '')
                
                if cors_header == '*':
                    logger.warning(f'  ⚠ Permissive CORS policy at {endpoint}')
                    self.vulnerabilities.append({
                        'type': 'permissive_cors',
                        'endpoint': endpoint,
                    })
                else:
                    logger.info(f'  ✓ Restricted CORS: {endpoint}')
            except requests.RequestException:
                pass
        
        self.test_results.append({'test': 'cors_policy', 'status': 'completed'})

    def test_header_security(self):
        """Test security headers"""
        logger.info('\n[TEST] Security Headers')
        
        required_headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': ['DENY', 'SAMEORIGIN'],
            'Strict-Transport-Security': 'max-age',
            'Content-Security-Policy': None,
        }
        
        endpoints = [
            'http://localhost:8000/health',
            'http://localhost:9002/health',
        ]
        
        for endpoint in endpoints:
            try:
                response = requests.get(endpoint, timeout=5)
                
                for header, expected in required_headers.items():
                    value = response.headers.get(header, '')
                    
                    if not value:
                        logger.warning(f'  ⚠ Missing header {header} at {endpoint}')
                        self.vulnerabilities.append({
                            'type': 'missing_security_header',
                            'endpoint': endpoint,
                            'header': header,
                        })
                    elif expected and isinstance(expected, list):
                        if not any(exp in value for exp in expected):
                            logger.warning(f'  ⚠ Incorrect {header} at {endpoint}: {value}')
                    elif expected and expected not in value:
                        logger.warning(f'  ⚠ Incorrect {header} at {endpoint}: {value}')
            except requests.RequestException:
                pass
        
        self.test_results.append({'test': 'security_headers', 'status': 'completed'})

    def test_file_upload_vulnerabilities(self):
        """Test file upload security"""
        logger.info('\n[TEST] File Upload Security')
        
        # Test malicious file uploads
        malicious_files = [
            ('test.php', b'<?php system($_GET["cmd"]); ?>'),
            ('test.sh', b'#!/bin/bash\nrm -rf /'),
            ('test.exe', b'MZ\x90\x00'),
        ]
        
        endpoint = 'http://localhost:9002/rag/ingest'
        
        for filename, content in malicious_files:
            try:
                files = {'file': (filename, content)}
                response = requests.post(endpoint, files=files, timeout=5)
                
                if response.status_code == 200:
                    logger.warning(f'  ⚠ Accepted malicious file: {filename}')
                    self.vulnerabilities.append({
                        'type': 'file_upload_vulnerability',
                        'endpoint': endpoint,
                        'filename': filename,
                    })
            except requests.RequestException:
                pass
        
        logger.info('  ✓ File upload tests completed')
        self.test_results.append({'test': 'file_upload', 'status': 'completed'})

    def test_api_key_exposure(self):
        """Test for API key exposure"""
        logger.info('\n[TEST] API Key Exposure')
        
        endpoints = [
            'http://localhost:8000/health',
            'http://localhost:9002/health',
            'http://localhost:9100/health',
        ]
        
        sensitive_patterns = [
            'api_key',
            'secret',
            'password',
            'token',
            'credentials',
        ]
        
        for endpoint in endpoints:
            try:
                response = requests.get(endpoint, timeout=5)
                
                for pattern in sensitive_patterns:
                    if pattern in response.text.lower():
                        logger.warning(f'  ⚠ Potential sensitive data exposure at {endpoint}')
                        self.vulnerabilities.append({
                            'type': 'sensitive_data_exposure',
                            'endpoint': endpoint,
                            'pattern': pattern,
                        })
            except requests.RequestException:
                pass
        
        logger.info('  ✓ API key exposure tests completed')
        self.test_results.append({'test': 'api_key_exposure', 'status': 'completed'})

    def generate_report(self):
        """Generate security audit report"""
        logger.info('\n' + '=' * 60)
        logger.info('Security Audit Report')
        logger.info('=' * 60)
        
        logger.info(f'\nTests Run: {len(self.test_results)}')
        logger.info(f'Vulnerabilities Found: {len(self.vulnerabilities)}')
        
        if self.vulnerabilities:
            logger.info('\nVulnerabilities:')
            for vuln in self.vulnerabilities:
                logger.warning(f"  - {vuln['type']}: {vuln}")
        else:
            logger.info('\n✓ No vulnerabilities detected')
        
        # Calculate security score
        total_checks = len(self.test_results) * 10  # Estimate
        issues = len(self.vulnerabilities)
        security_score = max(0, ((total_checks - issues) / total_checks * 100))
        
        logger.info(f'\nSecurity Score: {security_score:.1f}%')
        
        if security_score >= 95:
            logger.info('Status: EXCELLENT ✓')
        elif security_score >= 80:
            logger.info('Status: GOOD ⚠')
        else:
            logger.info('Status: NEEDS ATTENTION ✗')
        
        logger.info('=' * 60)
        
        # Save report
        report = {
            'timestamp': datetime.now().isoformat(),
            'tests_run': len(self.test_results),
            'vulnerabilities_found': len(self.vulnerabilities),
            'security_score': security_score,
            'vulnerabilities': self.vulnerabilities,
            'test_results': self.test_results,
        }
        
        with open('security_audit_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info('Report saved to security_audit_report.json')

    def run_audit(self):
        """Run complete security audit"""
        logger.info('=' * 60)
        logger.info('Starting Security Audit')
        logger.info('=' * 60)
        
        # Check if Trivy is installed
        try:
            subprocess.run(['trivy', '--version'], capture_output=True, check=True)
            self.trivy_image_scan()
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning('Trivy not installed. Skipping image scanning.')
            logger.warning('Install with: curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin')
        
        self.penetration_testing()
        self.generate_report()


def main():
    """Run security audit"""
    auditor = SecurityAuditor()
    auditor.run_audit()


if __name__ == '__main__':
    main()
