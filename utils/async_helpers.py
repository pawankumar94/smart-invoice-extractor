"""
Async helper functions for the OCR application.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

def run_async(coro):
    """Run an async function in a sync context"""
    try:
        return asyncio.run(coro)
    except Exception as e:
        logger.error(f"Async error: {str(e)}")
        return None 