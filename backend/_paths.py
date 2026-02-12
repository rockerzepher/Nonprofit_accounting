"""Resolve project paths reliably for both local dev and Vercel."""

import os

# Project root = parent of the 'backend' package directory
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_THIS_DIR)

TEMPLATES_DIR = os.path.join(_THIS_DIR, "templates")
STATIC_DIR = os.path.join(_THIS_DIR, "static")
