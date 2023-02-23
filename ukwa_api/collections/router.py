from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import FileResponse
from pathlib import Path
import os
import logging

# Create a logger, beneath the Uvicorn error logger:
logger = logging.getLogger(f"uvicorn.error.{__name__}")

JSON_DIR = os.environ.get("JSON_DIR","test/data/collections/")
JSON_DIR = JSON_DIR.rstrip("/") + "/"

# Setup a router:
router = APIRouter(
    prefix='/collections'
)

@router.get("/download/{collection_id}", status_code=200,
    summary="Download a collection extract in JSON format",
    description="""This returns a JSON file containing the collection specified by the entered id,
including all subcollections and target data."""
)
def download_file(collection_id: int):
    filepath = JSON_DIR + str(collection_id) + ".json"
    
    logger.debug(f"Looking for Collection JSON file {filepath}...")
    my_file = Path(filepath)
    if not my_file.is_file():
        raise HTTPException(status_code=404, detail="Collection " + str(collection_id) + " JSON not found.")
    
    return FileResponse(path=filepath, media_type='application/json', filename=my_file.name)


