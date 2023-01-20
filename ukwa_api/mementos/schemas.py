from enum import Enum
from typing import List, Optional, Any
from datetime import datetime

from pydantic import BaseModel, Field, AnyHttpUrl, EmailStr
from pydantic.utils import GetterDict

from fastapi import Path

class LookupMatchType(Enum):
    exact = 'exact'
    prefix = 'prefix'
    host = 'host'
    domain = 'domain'

class LookupSort(Enum):
    default = 'default'
    reverse = 'reverse'


#
#
#

path_ts = Path(
        ...,
        title='The 14-digit timestamp to use as a target. Will go to the most closest matching archived snapshot.',
        example='19950630120000',
        min_length=14,
        max_length=14,
        regex="^\d+$",
    )

path_url = Path(
        ...,
        title="URL to resolve.",
        description="...",
        example='http://portico.bl.uk/',
    )
