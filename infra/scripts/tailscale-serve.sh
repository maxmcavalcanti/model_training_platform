#!/usr/bin/env bash
# Declares which loopback ports are exposed as HTTPS on the tailnet (ADR 0003).
# Reset first, then reapply: the serve state on the VPS always matches git.
# One line per UI, same port on loopback and on the tailnet.
set -euo pipefail

tailscale serve reset

tailscale serve --bg --https=8080 http://127.0.0.1:8080
