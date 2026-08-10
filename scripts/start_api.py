"""Script to start the FastAPI backend server."""

import uvicorn
import sys
from pathlib import Path
import os

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def main():
    print("Starting Product Review Pulse API Server...")
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=True,
    )

if __name__ == "__main__":
    main()
