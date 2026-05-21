# EDAPT v2 Security Notes

---

## Prototype Limitations

This application is a localhost prototype. The following security measures are intentionally deferred for production implementation.

- **JWT storage** — Tokens are stored in `localStorage`, which is vulnerable to XSS. Production would use `httpOnly` cookies so tokens are inaccessible to JavaScript.
- **Token revocation** — The revocation list is stored in memory and resets on server restart. Production would use Redis for a persistent, distributed revocation store.
- **Data persistence** — User accounts and uploaded data are stored in memory and reset on server restart. Production would use PostgreSQL with proper migrations and backups.
- **HTTPS** — There is no TLS enforcement. Production would require valid TLS certificates and HTTP → HTTPS redirects.
- **Refresh tokens** — Sessions expire after a fixed period with no renewal. Production would implement sliding session renewal with short-lived access tokens and longer-lived refresh tokens stored in `httpOnly` cookies.

---

## Future Features

- **OTP email verification** — Designed for future implementation. The email validation infrastructure is in place on both frontend and backend. Activation requires SMTP integration with a service such as SendGrid or AWS SES.
- **Real-time collaborative features** — Would require WebSocket support for live dashboard updates and concurrent session awareness.

---

## Known Constraints

- **ML model inputs** — The pass-probability model uses two assessment inputs only, regardless of how many assessment types a subject has. Retraining with additional features (e.g. attendance, assignment count, subject difficulty) would improve prediction accuracy.
- **Gemini API rate limiting** — API calls have no persistent rate limiting. A high volume of requests can exhaust the API quota. Production would use Redis-backed rate limiting per user with configurable thresholds.
