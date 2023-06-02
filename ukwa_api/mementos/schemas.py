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


# note the pattern here is to specify the RANGE of leading characters or digits of the field value to be collapsed on
# not to specify otherwise the pattern of the field value itself. see description below for timestamp example
# it is more restrictive than the CDX endpoint, but meets sensible use cases following the CDX spec
path_collapse = Path(
    ...,
    description= '''CDX Field to collapse on, optionally with :number suffix to collapse on substring of field; 
                    in other words, return only the first/last row when of the series multiple consecutive rows
                    have the same value for the supplied field. Example: "timestamp:4" 
                    will return a single row per year (YYYY are the first 4 digits).''',          
    regex = (
        r"^(statuscode:([1-3])|digest:(?:[1-9]|[1-3][0-9]|40)|urlkey:([1-9][0-9]?)|"
        r"timestamp:(1[0-4]|[4-9])|mimetype:([1-9][0-9]?)|"
        r"original:([1-9][0-9]?)|redirecturl:([1-9][0-9]?)|"
        r"filename:([1-9][0-9]?)|robotflags:([1-9])|"
        r"offset:(?:[1-9]|1[0-2])|length:(?:[1-9]|1[0-2])|"
        r"(urlkey|timestamp|original|mimetype|statuscode|digest|length|offset|filename|redirecturl|robotflags)?)$"

    )
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