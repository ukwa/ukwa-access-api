from sqlalchemy.orm import Session

from . import models, schemas


def get_nomination(db: Session, nomination_id: str):
    return db.query(models.Nomination).filter(models.Nomination.id == nomination_id).first()

# Directly get a set of results:
def get_nominations(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Nomination).offset(skip).limit(limit).all()

# Set up the query for getting results, with fastapi-pagination handling pages etc.
def query_nominations(db: Session):
    return db.query(models.Nomination).order_by(models.Nomination.updated_at.desc())

def create_nomination(db: Session, nomination: schemas.NominationCreate):
    db_nom = models.Nomination(
	    url=nomination.url,
	    title=nomination.title,
	    name=nomination.name,
	    email=nomination.email,
	)
    for tag in nomination.tags:
        db_tag = db.query(models.Tag).filter(models.Tag.id == tag).first()
        if not db_tag:
            db_tag = models.Tag(id=tag)
        db_nom.tags.append(db_tag)
    db.add(db_nom)
    db.commit()
    db.refresh(db_nom)
    return db_nom