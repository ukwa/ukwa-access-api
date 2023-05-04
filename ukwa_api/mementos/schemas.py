from enum import Enum
from typing import List, Optional, Any

from pydantic import BaseModel, Field, AnyHttpUrl, EmailStr
from pydantic.utils import GetterDict

from fastapi import Path, Query

class LookupMatchType(Enum):
    exact = 'exact'
    prefix = 'prefix'
    host = 'host'
    domain = 'domain'

class LookupSort(Enum):
    default = 'default'
    reverse = 'reverse'
    closest = 'closest'

class LookupOutputType(str, Enum):
    cdx = 'cdx'
    json = 'json'

path_ts = Path(
        ...,
        description='The 14-digit timestamp to use as a target. Will go to the closest matching archived snapshot. Format YYYYMMDDHHMMSS.',
        example='19950630120000',
        min_length=14,
        max_length=14,
        regex="^\d+$",
    )

path_url = Path(
        ...,
        description="URL to resolve.",
        example='http://portico.bl.uk/',
    )

path_range_ts = Path(
    ...,
    description='Format YYYY, YYYYMM, etc., up to YYYYMMDDHHMMSS.',
    # example='19950630120000',
    min_length=4,  # Allow for partial matches
    max_length=14,
    regex="^\d{4,14}$",  # Allow 4-14 digits
)

path_collapse = Path(
    ...,
    description= '''CDX Field to collapse on, optionally with :number suffix to collapse on substring of field; 
                    in other words, return only the first/last row when of the series multiple consecutive rows
                    have the same value for the supplied field. Example: "timestamp:4" 
                    will return a single row per year (YYYY are the first 4 digits).''',
    # Allow 4-14 digits for timestamp, 1-3 for status code
    # note that in this case we are expecting a timestamp (string) _length_, 
    # rather than an actual _timestamp_ (of varying length) so the timestamp regex is different            
    regex="^(timestamp(:(1[0-4]|[4-9]))?|(statuscode(:[1-3])?))?$"
)

# allows us to reuse a basic param definition as a whole 
# rather than having having to reference the attibutes each time
def create_query_param_from_path(path: Path, alias: Optional[str] = None) -> Query:
    query_params = {
        'description': path.description,
        'min_length': path.min_length,
        'max_length': path.max_length,
        'regex': path.regex,
    }
    if alias is not None: # allow us to override for cdx params that might conflict with python keywords
        query_params['alias'] = alias
    return Query(None, **query_params)