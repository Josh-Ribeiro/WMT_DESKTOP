#!/usr/bin/env python3
"""
WMT Desktop - FastAPI Backend Entry Point
Runs on localhost:8000
"""

import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.main import app

if __name__ == "__main__":
    import uvicorn
    
    # Run FastAPI server
    # Accessible only from localhost for security
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
