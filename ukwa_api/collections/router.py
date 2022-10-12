from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import FileResponse
from pathlib import Path
import os

JSON_DIR = os.environ.get("JSON_DIR","./data/api/")

# Setup a router:
router = APIRouter(
    prefix='/collections'
)

@router.get("/download/{collection_id}", status_code=200 )
def download_file(collection_id: int):
    filepath = JSON_DIR + str(collection_id) + ".json"

    my_file = Path(filepath)
    if not my_file.is_file():
        raise HTTPException(status_code=404, detail="Collection " + str(collection_id) + " JSON not found.")
    
    return FileResponse(path=filepath, media_type='application/json', filename=my_file.name)


