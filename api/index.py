"""Vercel serverless entry point — exposes the FastAPI app as a handler."""

from main import app

# Vercel's Python runtime looks for `app` or `handler` at module level.
# FastAPI's ASGI interface is compatible with Vercel's Python runtime.
handler = app
