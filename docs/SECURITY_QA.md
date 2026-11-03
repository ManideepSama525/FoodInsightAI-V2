# Phase 8 — Security and quality assurance

## Implemented controls

- Explicit CORS origin allowlist; wildcard origins are rejected because credentialed requests are enabled.
- CORS methods limited to GET and POST, and headers limited to Content-Type and Authorization.
- Security response headers: MIME sniffing protection, frame denial, referrer policy, permissions policy, and a restrictive API content security policy.
- HSTS is added only when `APP_ENV=production`; production deployment must terminate HTTPS correctly.
- Interactive API documentation and OpenAPI endpoints are disabled in production mode.
- Readiness endpoint now performs a real database connectivity probe and returns HTTP 503 when unavailable.
- Upload validation checks actual decoded image format, declared MIME consistency, byte limit, pixel limit, and Pillow decompression-bomb warnings.
- Upload storage names are generated server-side; original filenames are not used as filesystem paths.
- USDA failures return a generic client-facing message; API keys are not included in application response payloads.

## Tests

`backend/tests/test_security.py` covers CORS validation, upload size, image bytes, MIME mismatch, and valid image acceptance. Run all backend tests with:

```bash
python -m pip install -e ".[dev]"
python -m pytest backend/tests -q
```

## Deployment security checklist

- Set a unique production `CORS_ORIGINS` value to the exact HTTPS frontend origin(s).
- Set `APP_ENV=production` only behind HTTPS/TLS termination.
- Keep `.env`, database files, uploads, datasets, and model artifacts outside source control.
- Supply `USDA_API_KEY` through environment/secrets management; rotate it if exposed.
- Use a managed database account with least privilege and backups.
- Restrict upload directory permissions and enforce reverse-proxy request-body limits.
- Add a production rate limiter (shared Redis/API gateway), monitoring, log redaction, and malware scanning before public internet exposure. The current application does not implement distributed rate limiting.
- Do not expose this development build publicly until the deployment checklist is completed.

## Known limitations

The API uses synchronous SQLAlchemy sessions for database operations. In-memory test databases are not a production database recommendation. The application does not yet include user authentication, authorization, account isolation, distributed rate limiting, or malware scanning. These must be designed before multi-user public deployment.
