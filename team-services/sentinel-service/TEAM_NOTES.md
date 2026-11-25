# Sentinel source staging (NOT deployment-ready)

Source is copied from the restricted Sentinel review ZIP.
No model weights, credentials, logs, or database files included.

The application's /login endpoint is a dummy, and /seed is unauthenticated.
Do not expose the service to other hosts; use 127.0.0.1 only.
Security bridge tokens, controlled startup, runtime database location,
and model assets must be configured and validated separately.
