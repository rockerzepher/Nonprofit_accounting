"""Vercel serverless entry point — exposes the FastAPI app."""

import sys
import os

# Ensure the project root is on sys.path so 'backend' package resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402

# Vercel's Python runtime looks for `app` at module level.
