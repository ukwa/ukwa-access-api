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


class CollapseType(str, Enum):
    default = ''
    collapseToFirst = 'collapseToFirst'
    collapseToLast = 'collapseToLast'

class CollapseField(str, Enum):
    default = ''
    urlkey = 'urlkey'
    timestamp = 'timestamp'
    original = 'original'
    mimetype = 'mimetype'
    statuscode = 'statuscode'
    digest = 'digest'
    length = 'length'


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

# allows us to reuse the timestamp definition as a whole 
# rather than having having to reference the attibutes each time
def create_query_from_path(path: Path) -> Query:
    return Query(
        None,
        description=path.description,
        min_length=path.min_length,
        max_length=path.max_length,
        regex=path.regex,
    )

