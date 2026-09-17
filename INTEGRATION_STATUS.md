# Qwen Coach integration

This branch is intentionally isolated from `main`.

The current GitHub repository snapshot contained only a 33-byte README, so there was no application source to modify safely. This branch therefore adds a standalone, production-oriented Coach module that is ready to be integrated once the current application source is synced here.

## Included

- Qwen server-side integration
- persistent SQLite conversations
- explicit user memory
- authenticated Coach UI
- four Coach modes
- health endpoint
- rate limiting and input limits
- security headers
- unit tests with mocked Qwen
- GitHub Actions CI
- CT105 systemd unit

## Safety

`main` has not been modified. No existing application code was overwritten.

## Required before production merge

1. Sync the actual current application source into this repository.
2. Integrate the Coach module into the existing navigation rather than replacing the application shell.
3. Configure `QWEN_API_KEY`, `COACH_PASSWORD`, and `COACH_SESSION_SECRET` on CT105.
4. Put the service behind HTTPS/reverse proxy.
5. Run the full application test/build suite after integration.
