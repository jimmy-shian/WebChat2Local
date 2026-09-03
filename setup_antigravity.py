"""
1-Click Antigravity Setup Script for Gemini Web to Local Bridge.
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.antigravity.installer import install_antigravity_integration

if __name__ == "__main__":
    print("=" * 60)
    print(" Installing Gemini Web Bridge for Google Antigravity...")
    print("=" * 60)
    result = install_antigravity_integration()
    print(f"[OK] Project MCP Config: {result['project_mcp_config']}")
    print(f"[OK] Project Skill:      {result['skill_path']}")
    print(f"[OK] Project Rule:       {result['rules_path']}")
    print(f"[OK] Global Registered:  {result['global_installed']}")
    print("=" * 60)
    print(" Antigravity Integration setup completed successfully!")
    print("=" * 60)
