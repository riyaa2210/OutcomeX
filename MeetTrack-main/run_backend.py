#!/usr/bin/env python
"""
Backend startup script for Meeting Outcome Tracker
"""

import os
import sys
import subprocess

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    
    print("=" * 50)
    print("Meeting Outcome Tracker - Backend Startup")
    print("=" * 50)
    
    # Check if dependencies are installed
    print("\n[1/2] Checking dependencies...")
    try:
        import dotenv
        import fastapi
        import sqlalchemy
        import uvicorn
        print("✅ All dependencies are installed")
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Installing dependencies from requirements.txt...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installed")
    
    # Start the backend server
    print("\n[2/2] Starting FastAPI backend server...")
    print("-" * 50)
    print("Backend will be available at: http://127.0.0.1:8000")
    print("API Documentation: http://127.0.0.1:8000/docs")
    print("-" * 50)
    
    # Run uvicorn from project root with full module path
    # Run uvicorn
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "backend.app.main:app",
        "--reload",
        "--host", "127.0.0.1",
        "--port", "8000"
    ])

if __name__ == "__main__":
    main()
