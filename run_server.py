"""
Entrypoint runner for Gemini Web to Local Bridge.
Usage:
  python run_server.py [start|status|mcp|setup|chat]
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.cli import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Default action with no args: start server
        sys.argv.append("start")
    main()
