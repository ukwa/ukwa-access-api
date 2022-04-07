from enum import Enum
from typing import List, Optional, Any
from datetime import datetime

from pydantic import BaseModel, Field, AnyHttpUrl, EmailStr
from pydantic.utils import GetterDict

class LookupMatchType(Enum):
    exact = 'exact'
    prefix = 'prefix'
    host = 'host'
    domain = 'domain'
    range = 'range'

class LookupSort(Enum):
    default = 'default'
    closest = 'closest'
    reverse = 'reverse'