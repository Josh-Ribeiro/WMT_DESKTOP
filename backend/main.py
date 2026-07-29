#!/usr/bin/env python3
"""
WMT Desktop - FastAPI Backend Entry Point
Runs on localhost:8000
"""

import sys
import os
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.main import app

if __name__ == "__main__":
    import uvicorn
    
    development = (
        os.getenv("WMT_DEV", "").strip().lower() in {"1", "true", "yes"}
        and not getattr(sys, "frozen", False)
    )
    uvicorn.run(
        "app.main:app",
        host=os.getenv("WMT_BACKEND_HOST", "127.0.0.1"),
        port=int(os.getenv("WMT_BACKEND_PORT", "8000")),
        reload=development,
        log_level="info"
    )
