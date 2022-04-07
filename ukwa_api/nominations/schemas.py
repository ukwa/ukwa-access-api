from typing import List, Optional, Any
from datetime import datetime

from pydantic import BaseModel, Field, AnyHttpUrl, EmailStr
from pydantic.utils import GetterDict

from fastapi import APIRouter

# As SQLAlchemy requires a Tag model, this needs mapping to a string array:
class NominationGetter(GetterDict):

    # Helper method to get app context for href: 
    @classmethod
    def init_router(cls, router: APIRouter):
       cls._router = router

    def get(self, key:str, default: Any) -> Any:
        if key == 'tags':
            tags = []
            for t in self._obj.tags:
                tags.append(t.id)
            return tags
        elif key == 'href':
            return self._router.url_path_for('get_nomination', nomination_id=self._obj.id)
        else:
            return getattr(self._obj, key)

# This is the base class with shared fields.
class NominationBase(BaseModel):
    url: AnyHttpUrl = Field(..., example="https://example.com/")
    title: Optional[str] = Field(None, example="An Example Website")

# These are the fields of the record that can be viewed publicly:
class Nomination(NominationBase):
    id: str
    href: str
    status: Optional[str] = None
    tags: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        getter_dict = NominationGetter

# These are the fields that can be submitted when creating a record:
class NominationCreate(NominationBase):
    name: Optional[str] = Field(None, example="Name of Nominator and/or Website Contact")
    email: Optional[EmailStr] = Field(None, example="Contact Email Address")
    note: Optional[str] = Field(None, example="Note of any additional information.")
    tags: List[str] = Field(None, example='["example", "test"]')

    class Config:
        orm_mode = True