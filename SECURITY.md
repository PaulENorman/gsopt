# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

**DO NOT** create a public GitHub issue for security vulnerabilities.

Instead, email security reports to: [your-email@gmail.com]

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive a response within 48 hours.

## Security Measures

### Authentication
- All endpoints require a valid 'X-User-Email' header
- Only @gmail.com email domains are allowed
- Infrastructure ensures requests originate from authorized Google Workspace environments
- No user tokens or PII are stored on the server (stateless architecture)

### Input Validation
- All user inputs are validated and sanitized
- Parameter names restricted to alphanumeric + underscore/hyphen
- Numeric bounds validated to prevent overflow
- Request size limited to 10MB
- Maximum parameter count: 100
- Maximum data points: 10,000

### Rate Limiting
- Ping endpoint: 10 requests per 60 seconds per user
- Prevents abuse and resource exhaustion

### Security Headers
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection enabled
- Strict-Transport-Security (HSTS)
- Content-Security-Policy
- No-cache headers for sensitive data

### Dependencies
- Regular security updates via Dependabot
- Minimal dependency footprint
- Only trusted, well-maintained packages

### Cloud Run Security
- Private service (requires authentication)
- No public internet access
- Runs in Google's secure infrastructure
- Automatic HTTPS enforcement
- Container scanning enabled

## Best Practices for Users

1. **Never share your Google OAuth tokens**
2. **Use the official Google Sheet template only**
3. **Don't modify authentication code in Apps Script**
4. **Report suspicious activity immediately**
5. **Keep your Google Sheets add-on updated**
