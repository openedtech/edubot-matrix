import logging
import sqlite3
from typing import Any, Dict

import g

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

        # Try to check the current migration version
        migration_level = 0
        try:
            self._execute("SELECT version FROM migration_version")
            row = self.cursor.fetchone()
            migration_level = row[0]
        except Exception:
            self._initial_setup()
        finally:
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

        # Set up any other necessary database tables here

        self._execute(
            """
            CREATE TABLE IF NOT EXISTS admin (
                admin_id STRING PRIMARY KEY
            );
            
            CREATE TABLE IF NOT EXISTS room  (
                room_id STRING PRIMARY KEY,
                personality STRING
            );
            
            -- Joiner table to allow many-many relationship between room & admin
            CREATE TABLE IF NOT EXISTS room_admin (
                admin_id FOREIGN KEY REFERENCES admin.user_id PRIMARY KEY,
                room_id FOREIGN KEY references room.room_id PRIMARY KEY
            );
            """
        )

        self.conn.commit()

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
            """, (room_id,)
        )
        self.conn.commit()

    def add_room_admin(self, room_id: str, admin_id: str) -> None:
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
            """
            , (admin_id,)
        )
        self._add_room_to_db(room_id)

        # Make an admin of the room, if they are not already.
        self._execute(
            """
            INSERT OR IGNORE INTO room_admin(admin_id, room_id)
            VALUES (?, ?);
            """
            , (admin_id, room_id)
        )

        self.conn.commit()

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
                """, (room_id, admin_id)
            )
            self.conn.commit()
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
            """, (room_id,)
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

        return (user_id in self.list_room_admins(room_id)  # If the user is an admin in this room
                or user_id in g.config.admins)  # OR the user is a hard-coded super-admin

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
            """, (personality, room_id)
        )
        self.conn.commit()
