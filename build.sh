#!/usr/bin/env bash
# Convenience wrapper — delegates to setup.sh
cd "$(cd "$(dirname "$0")" && pwd)"
exec bash setup.sh "$@"
