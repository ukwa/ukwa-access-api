# -*- coding: utf-8 -*-
"""
This file declares the routes for the Crawls module.
"""
import os
import json
import logging

from fastapi import Depends, FastAPI, HTTPException, APIRouter, status, Request, Response, Query

# Create a logger, beneath the Uvicorn error logger:
logger = logging.getLogger(f"uvicorn.error.{__name__}")

# Setup a router:
router = APIRouter(
    prefix='/crawls'
)

#
# Set up the router
#
@router.get("/fc/recent-activity",
    summary="Recent crawl stats",
    description="""
This returns a summary of recent crawling activity from the 'fc' or 'frequent crawl'.
    """
)
async def get_recent_activity():
    with open(os.environ.get("ANALYSIS_SOURCE_FILE", "test/data/fc.crawled.json")) as f:
        stats = json.load(f)
    return stats


