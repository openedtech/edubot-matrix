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

import logging
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict

from edubot_matrix import g
from edubot_matrix.types import FeedInfo
from edubot_matrix.utils import unix_utc

# The latest migration version of the database.
#
# Database migrations are applied starting from the number specified in the database's
# `migration_version` table + 1 (or from 0 if this table does not yet exist) up until
# the version specified here.
#
# When a migration is performed, the `migration_version` table should be incremented.
latest_migration_version = 0

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, database_config: Dict[str, str]):
        """Set up the database.

        Runs an initial setup or migrations depending on whether a database file has already
        been created.

        Args:
            database_config: a dictionary containing the following keys:
                * type: A string, one of "sqlite" or "postgres".
                * connection_string: A string, featuring a connection string that
                    be fed to each respective db library's `connect` method.
        """
        self.conn = self._get_database_connection(
            database_config["type"], database_config["connection_string"]
        )
        self.cursor = self.conn.cursor()
        self.db_type = database_config["type"]

        self._initial_setup()

        # Try to check the current migration version
        self._execute("SELECT version FROM migration_version")
        row = self.cursor.fetchone()
        migration_level = row[0]

        if migration_level < latest_migration_version:
            self._run_migrations(migration_level)

        logger.info(f"Database initialization of type '{self.db_type}' complete")

    def _get_database_connection(
        self, database_type: str, connection_string: str
    ) -> Any:
        """Creates and returns a connection to the database"""
        if database_type == "sqlite":
            import sqlite3

            # Initialize a connection to the database, with autocommit on
            return sqlite3.connect(connection_string, isolation_level=None)
        elif database_type == "postgres":
            import psycopg2

            conn = psycopg2.connect(connection_string)

            # Autocommit on
            conn.set_isolation_level(0)

            return conn

    def _initial_setup(self) -> None:
        """Initial setup of the database"""
        logger.info("Performing initial database setup...")

        # Make sure Foreign key constraints are checked.
        self._execute("PRAGMA foreign_keys = ON;")

        # Set up the migration_version table
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS migration_version (
                version INTEGER PRIMARY KEY
            )
            """
        )

        # Initially set the migration version to 0
        self._execute(
            """
            INSERT OR IGNORE INTO migration_version (
                version
            ) VALUES (?)
            """,
            (0,),
        )

        self._execute(
            """
            CREATE TABLE IF NOT EXISTS admin (
                admin_id STRING PRIMARY KEY
            );
            """
        )

        self._execute(
            """
            CREATE TABLE IF NOT EXISTS room  (
                room_id STRING PRIMARY KEY,
                personality STRING
            );
            """
        )

        self._execute(
            """
            -- Joiner table to allow many-many relationship between room & admin
            CREATE TABLE IF NOT EXISTS room_admin (
                admin_id STRING,
                room_id STRING,
                PRIMARY KEY (admin_id, room_id),
                FOREIGN KEY (admin_id) REFERENCES admin(admin_id) ON DELETE CASCADE,
                FOREIGN KEY (room_id) references room(room_id) ON DELETE CASCADE
            );
            """
        )

        self._execute(
            """
            CREATE TABLE IF NOT EXISTS rss_feed (
            url STRING PRIMARY KEY,
            -- Last time the feed was updated
            last_update INTEGER NOT NULL
            )
            """
        )

        self._execute(
            """
            CREATE TABLE IF NOT EXISTS rss_subscription (
            url STRING,
            room_id STRING,
            PRIMARY KEY (url, room_id),
            FOREIGN KEY (url) references rss_feed(url) ON DELETE CASCADE,
            FOREIGN KEY (room_id) references room(room_id) ON DELETE CASCADE
            )

            """
        )

        self.conn.commit()

        logger.info("Database setup complete")

    def _run_migrations(self, current_migration_version: int) -> None:
        """Execute database migrations. Migrates the database to the
        `latest_migration_version`.

        Args:
            current_migration_version: The migration version that the database is
                currently at.
        """
        logger.debug("Checking for necessary database migrations...")

        # if current_migration_version < 1:
        #    logger.info("Migrating the database from v0 to v1...")
        #
        #    # Add new table, delete old ones, etc.
        #
        #    # Update the stored migration version
        #    self._execute("UPDATE migration_version SET version = 1")
        #
        #    logger.info("Database migrated to v1")

    def _execute(self, *args) -> None:
        """A wrapper around cursor.execute that transforms placeholder ?'s to %s for postgres.

        This allows for the support of queries that are compatible with both postgres and sqlite.

        Args:
            args: Arguments passed to cursor.execute.
        """
        if self.db_type == "postgres":
            self.cursor.execute(args[0].replace("?", "%s"), *args[1:])
        else:
            self.cursor.execute(*args)

    def _add_room_to_db(self, room_id: str) -> None:
        """
        Adds a room to the database if it doesn't already exist

        Args:
            room_id: A Matrix room ID
        """

        self._execute(
            """
            INSERT OR IGNORE INTO room(room_id)
            VALUES (?);
            """,
            (room_id,),
        )
        self.conn.commit()
        logger.info(f"Added room '{room_id}' to DB")

    def set_room_admin(self, room_id: str, admin_id: str) -> None:
        """
        Adds an admin to a room

        Args:
            room_id: The room ID that the user is an admin of
            admin_id: The user ID of the admin
        """

        # Insert admin and room into DB if they aren't already
        self._execute(
            """
            INSERT OR IGNORE INTO admin(admin_id)
            VALUES (?);
            """,
            (admin_id,),
        )
        self._add_room_to_db(room_id)

        # Make an admin of the room, if they are not already.
        self._execute(
            """
            INSERT OR IGNORE INTO room_admin(admin_id, room_id)
            VALUES (?, ?);
            """,
            (admin_id, room_id),
        )

        self.conn.commit()
        logger.info(f"New admin '{admin_id}' in '{room_id}'")

    def remove_room_admin(self, room_id, admin_id):
        """
        Delete an admin from a room.

        Args:
            room_id: A Matrix room ID.
            admin_id: A Matrix user ID.
        """
        try:
            self._execute(
                """
                DELETE FROM room_admin
                WHERE room_id = (?)
                AND admin_id = (?);
                """,
                (room_id, admin_id),
            )
            self.conn.commit()
            logger.info(f"Removed admin '{admin_id}' in '{room_id}'")
        # If admin_id was not an admin of room_id, silently ignore.
        except sqlite3.OperationalError:
            pass

    def list_room_admins(self, room_id: str) -> list[str]:
        """
        Get a list of admins for a particular room.

        Args:
            room_id: A Matrix room ID.
        """

        self._execute(
            """
            SELECT (admin_id) FROM room_admin
            WHERE room_id = (?);
            """,
            (room_id,),
        )

        raw_list: list[tuple[str]] = self.cursor.fetchall()

        # Unpack list of tuples
        return [i[0] for i in raw_list]

    def check_if_admin(self, room_id: str, user_id: str) -> bool:
        """
        Check if someone has admin rights in a particular room.

        Args:
            room_id: A Matrix room ID.
            user_id: A Matrix user ID.
        """
        # If the user is an admin in this room OR the user is a hard-coded super-admin
        is_admin = (
            user_id in self.list_room_admins(room_id) or user_id in g.config.admins
        )

        return is_admin

    def set_personality(self, room_id: str, personality: str) -> None:
        """
        Change the Bot's personality for a room.

        Args:
            room_id: A Matrix room ID.
            personality: The personality string to set.
        """
        self._add_room_to_db(room_id)
        self._execute(
            """
            UPDATE room
            SET personality = (?)
            WHERE room_id = (?);
            """,
            (personality, room_id),
        )
        self.conn.commit()
        logger.info(f"Set personality '{personality}' in '{room_id}'")

    def get_personality(self, room_id: str) -> str:
        """
        Gets the personality for a room.

        Args:
            room_id: A Matrix room ID.

        Returns:
            A personality string.
        """
        self._execute(
            """
            SELECT personality FROM room
            WHERE room_id = ?;
            """,
            (room_id,),
        )

        personality: str | None = self.cursor.fetchone()[0]

        if personality is None:
            personality = ""

        return personality

    def add_rss_feed(self, room_id: str, rss_url: str) -> None:
        """
        Adds an RSS feed subscription to a room.

        Args:
            room_id: A Matrix room ID.
            rss_url: The URL of an RSS feed.
        """
        self._add_room_to_db(room_id)

        self._execute(
            """
            INSERT OR IGNORE INTO rss_feed(url, last_update)
            VALUES (?, ?);
            """,
            (rss_url, unix_utc()),
        )

        self._execute(
            """
            INSERT OR IGNORE INTO rss_subscription(room_id, url)
            VALUES (?, ?)
            """,
            (room_id, rss_url),
        )

        self.conn.commit()
        logger.info(f"Subscribed to feed '{rss_url}' in '{room_id}'")

    def remove_rss_feed(self, room_id: str, rss_url: str) -> None:
        """
        Removes an RSS feed subscription from a room.

        Args:
            room_id: A Matrix room ID.
            rss_url: The URL of an RSS feed.
        """

        self._execute(
            """
            DELETE FROM rss_subscription
            WHERE room_id = ?
            AND url = ?;
            """,
            (room_id, rss_url),
        )
        self.conn.commit()
        logger.info(f"Unsubscribed from feed '{rss_url}' in '{room_id}'")

    def get_feeds_from_room(self, room_id: str) -> list[str]:
        """
        List the rss feeds a room is subscribed to.

        Args:
            room_id: A Matrix room ID.

        Returns:
            A list of RSS feed URLS.
        """

        self._execute(
            """
            SELECT url FROM rss_subscription
            WHERE room_id = ?;
            """,
            (room_id,),
        )
        raw_list: list[tuple[str]] = self.cursor.fetchall()

        # Unpack list of tuples
        return [i[0] for i in raw_list]

    def get_rooms_from_feed(self, rss_url: str) -> list[str]:
        """
        Get all the rooms subscribed to an RSS feed.

        Args:
            rss_url: The URL of an RSS feed.

        Returns:
            A list of Matrix room ID's.
        """
        self._execute(
            """
            SELECT room_id FROM rss_subscription
            WHERE url = ?;
            """,
            (rss_url,),
        )

        raw_list: list[tuple[str]] = self.cursor.fetchall()

        # Unpack list of tuples
        return [i[0] for i in raw_list]

    def list_rss_feeds(self) -> list[FeedInfo]:
        """
        Get all the RSS feeds currently subscribed to.

        Returns:
            A list of FeedInfo dicts.
        """

        self._execute(
            """
            SELECT DISTINCT s.url, f.last_update FROM rss_subscription s
            JOIN rss_feed f ON s.url = f.url;
            """
        )

        return [
            {"url": i[0], "last_update": datetime.fromtimestamp(i[1])}
            for i in self.cursor.fetchall()
        ]

    def set_rss_last_update(self, rss_url: str) -> None:
        """
        Changes the last_update value of an RSS feed.

        Args:
            rss_url: The URL of an RSS feed.
        """
        self._execute(
            """
            UPDATE rss_feed
            SET last_update = ?
            WHERE url = ?;
            """,
            (round(time.time()), rss_url),
        )
        self.conn.commit()
