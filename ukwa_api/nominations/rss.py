from enum import Enum
from typing import List

from fastapi_rss import (
    RSSFeed, RSSResponse, Item, Category, CategoryAttrs,
)

from . import models


class ResponseFormat(str, Enum):
    json = "json"
    rss = "rss"


def nominations_to_rss(nominations: List[models.Nomination]):
    items = []
    for nomination in nominations:
        items.append( Item(title=f"Nominated URL: {nomination.url}") )

    feed = RSSFeed(
        title='Test Feed',
        link='http://woo',
        description='ohyeah',
        item=items
    )

    return RSSResponse(feed)