from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()

def gen_uuid_str():
	return str(uuid.uuid4())

# Following https://docs.sqlalchemy.org/en/14/orm/basic_relationships.html#many-to-many

association_table = Table('nominations_tags', Base.metadata,
    Column('nomination_id', ForeignKey('nominations.id')),
    Column('tag_id', ForeignKey('tags.id'))
)

class Nomination(Base):
    __tablename__ = "nominations"

    id = Column(String, primary_key=True, index=True, default=gen_uuid_str)
    url = Column(String, unique=False, index=True)
    title = Column(String, unique=False, index=True)
    name = Column(String, unique=False, index=True)
    email = Column(String, unique=False, index=True)
    note = Column(String, unique=False, index=True)
    status = Column(String, unique=False, index=True)
    tags = relationship("Tag",
        secondary=association_table,
		backref="nominations")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

class Tag(Base):
    __tablename__ = 'tags'
    id = Column(String, primary_key=True, index=True)

