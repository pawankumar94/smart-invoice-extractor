#!/usr/bin/env python3
"""
Run script for the OCR application
"""

import os
import sys
import logging
from pathlib import Path

# Add the parent directory to the Python path to enable absolute imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Main function to run the Streamlit app"""
    try:
        # Import streamlit CLI module
        import streamlit.web.cli as stcli
        
        # Get the absolute path to app.py
        app_path = str(Path(__file__).parent / "app.py")
        logger.info(f"Starting Streamlit app from: {app_path}")
        
        # Set environment variables for Streamlit
        os.environ["STREAMLIT_SERVER_PORT"] = "8502"
        os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
        
        # Run Streamlit
        sys.argv = ["streamlit", "run", app_path, "--server.port=8502", "--global.developmentMode=false"]
        stcli.main()
    except Exception as e:
        logger.error(f"Error starting Streamlit app: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 