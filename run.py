#!/usr/bin/env python
"""Convenience script to run the Solar Load Controller locally."""

import os
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

import uvicorn
from app.main import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "run:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=True,
        reload_dirs=["app"],
    )
