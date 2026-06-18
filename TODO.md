# HTTPS Forcing Fix - TODO

- [x] Inspect settings for HTTPS/HSTS/proxy-ssl related config.

- [x] Edit `municipal_ai/settings.py` to explicitly disable HTTPS forcing and secure cookies.

- [x] Ensure no SECURE_PROXY_SSL_HEADER or SECURE_HSTS_* settings are present.

- [x] Search repo again for any remaining `https://127.0.0.1:8000` / `https://localhost:8000` references.

- [x] Restart Django server (attempted) — fails due to MySQL socket not reachable.

- [x] Started restart attempt; server failed because MySQL socket `/run/mysqld/mysqld.sock` not reachable (unrelated to HTTPS).
- [x] Verified Django HTTPS forcing flags are set to disable redirects/secure cookies.


- [x] Provide steps to clear browser site data/HSTS for localhost.

- [x] Added project-local `.env` with SECRET_KEY + DB settings placeholders.




