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

# Get the crawler stats file:
def load_fc_analysis():
    with open(os.environ.get("ANALYSIS_SOURCE_FILE", "test/data/fc.crawled.json")) as f:
        stats = json.load(f)
    return stats


#
# Set up the router
#
@router.get("/fc/recent-activity",
    summary="Recent crawl stats",
    description="""
This returns a summary of recent crawling activity.
    """
)
async def get_recent_activity():
        stats = load_fc_analysis()
        try:
            return stats
        except Exception as e:
            logger.exception("Could not jsonify stats: %s" % stats)


