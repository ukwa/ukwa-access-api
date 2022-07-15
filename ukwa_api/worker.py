from starlette.config import Config
from uvicorn.workers import UvicornWorker

config = Config()

class UkwaApiWorker(UvicornWorker):
    """
    Define a UvicornWorker, configured appropriately for the UKWA API.
    """

    CONFIG_KWARGS = {
        "root_path": config("SCRIPT_NAME", default=""),
        "proxy_headers": True,
        "forwarded_allow_ips": "*",
    }