# Qwen Coach integration

This branch is intentionally isolated from `main`.

The current GitHub repository snapshot contained only the original README, so there was no application source to modify safely. This branch adds a standalone, production-oriented Coach implementation rather than replacing or guessing at the unseen application.

Included: Qwen server integration, SQLite chat history, explicit memory, authenticated responsive UI, four Coach modes, health endpoint, rate/input limits, security headers, unit tests with mocked Qwen, GitHub Actions CI, and a CT105 systemd unit.

`main` has not been modified. No existing application code was overwritten.

Before production merge, sync the actual current application source into this repository, integrate the Coach behind the existing navigation, configure secrets on CT105, put it behind HTTPS/reverse proxy, and run the full application build/test suite.
