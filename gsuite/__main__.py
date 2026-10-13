"""`python -m gsuite …` — same CLI as the `gsuite` console script.

Added 2026-10-12 so hosts that only allow launching an interpreter (Langflow's MCP stdio
allow-list: python/node/npx/uvx, no console scripts, no `-c`) can still start the server:
    /home/j/projects/gsuite/.venv/bin/python -m gsuite serve
"""
import sys

from gsuite.cli import main

sys.exit(main())
