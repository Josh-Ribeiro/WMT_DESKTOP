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
    
    # Run FastAPI server
    # Accessible only from localhost for security
    development = os.getenv("WMT_DEV", "").strip().lower() in {"1", "true", "yes"}
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=development,
        log_level="info"
    )
