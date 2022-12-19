"""
Functions relating to RSS feeds.
"""
from datetime import datetime
from time import mktime
from typing import TypedDict

import feedparser


class FeedEntry(TypedDict):
    url: str
    title: str
    description: str


class FeedInfo(TypedDict):
    url: str
    last_update: datetime


def get_rss_updates(feed_infos: list[FeedInfo]) -> list[FeedEntry]:
    """

    Returns:

    """
    new_feed_entries: list[FeedEntry] = []

    for feed_info in feed_infos:
        url: str = feed_info["url"]
        last_update: datetime = feed_info["last_update"]

        parsed = feedparser.parse(url)

        items = [
            entry
            for entry in parsed.entries
            if datetime.fromtimestamp(mktime(entry.updated_parsed)) > last_update
        ]

        for item in items:
            pass
