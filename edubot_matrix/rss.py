# This file is part of edubot-matrix - https://github.com/openedtech/edubot-matrix
#
# edubot-matrix is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# edubot-matrix is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with edubot-matrix.  If not, see <http://www.gnu.org/licenses/>.
"""
Functions relating to RSS feeds.
"""
import asyncio
import logging
from calendar import timegm
from datetime import datetime

import feedparser
from nio.client.async_client import AsyncClient

from edubot_matrix.storage import Storage
from edubot_matrix.types import FeedEntry, FeedInfo
from edubot_matrix.utils import send_text_to_room

logger = logging.getLogger(__name__)


def validate_rss_url(rss_url: str) -> bool:
    """Validate a string is a valid RSS feed url."""
    feed = feedparser.parse(rss_url)
    if feed["bozo"]:
        return False

    return True


def get_rss_updates(feed_infos: list[FeedInfo]) -> list[FeedEntry]:
    """
    Get all the new entries in a list of RSS feeds.

    Returns:
        A list of FeedEntry.
    """
    new_feed_entries: list[FeedEntry] = []

    for feed_info in feed_infos:
        url: str = feed_info["url"]
        last_update: datetime = feed_info["last_update"]

        parsed = feedparser.parse(url)

        if parsed["bozo"]:
            logger.error(f"Could not parse feed {url}")
            continue

        feed_info["name"] = parsed.feed.title

        items = [
            entry
            for entry in parsed.entries
            if timegm(entry.updated_parsed) > last_update.timestamp()
        ]

        for item in items:
            new_feed_entries.append(
                {
                    "feed": feed_info,
                    "url": item.get("link", ""),
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                }
            )

    return new_feed_entries


async def sync_rss_feeds(client: AsyncClient, store: Storage) -> None:
    """
    Syncs RSS feeds and sends the latest changes to rooms on an interval.
    This function runs in an infinite loop.

    Args:
        client: An instance of the AsyncClient class.
        store: An instance of the Storage class.
    """

    while True:
        # Wait 10 minutes before repeating
        await asyncio.sleep(10 * 60)
        logger.info("Syncing RSS feeds")
        updates: list[FeedEntry] = get_rss_updates(store.list_rss_feeds())

        for update in updates:
            store.set_rss_last_update(update["feed"]["url"])
            # Get all the rooms subscribed to this feed
            for room_id in store.get_rooms_from_feed(update["feed"]["url"]):
                await send_text_to_room(
                    client,
                    room_id,
                    # A zero width space is added to the beginning of the feed name.
                    # This stops feed names starting with hashtags being converted into markdown headers.
                    f"&#8203;{update['feed']['name']}: [{update['title']}]({update['url']})",
                )

        logger.info("Done syncing RSS feeds")
