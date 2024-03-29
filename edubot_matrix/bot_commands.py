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
# along with edubot-matrix .  If not, see <http://www.gnu.org/licenses/>.

import logging

from nio import (
    AsyncClient,
    JoinedMembersError,
    JoinedMembersResponse,
    MatrixRoom,
    RoomMessageText,
)

from edubot_matrix import g
from edubot_matrix.config import Config
from edubot_matrix.rss import validate_rss_url
from edubot_matrix.storage import Storage
from edubot_matrix.utils import id_to_username, send_text_to_room

logger = logging.getLogger(__name__)


class Command:
    def __init__(
        self,
        client: AsyncClient,
        store: Storage,
        config: Config,
        command_and_args: str,
        room: MatrixRoom,
        event: RoomMessageText,
    ):
        """A command made by a user.

        Args:
            client: The client to communicate to matrix with.

            store: Bot storage.

            config: Bot configuration parameters.

            command_and_args: The command and arguments.

            room: The room the command was sent in.

            event: The event describing the command.
        """
        self.client = client
        self.store = store
        self.config = config
        self.room = room
        self.event = event
        self.is_admin = store.check_if_admin(self.room.room_id, self.event.sender)
        self.raw_message_lst: list[str] = command_and_args.split(" ")

        # Remove empty strings from list
        self.raw_message_lst = [i for i in self.raw_message_lst if i]

        # The attributes below are initialised in process() because async features are not allowed in __init__()
        self.command = ""
        self.args: list[str] = []

        # User ID's of all the members in this room.
        self.members: list[str] = []

    async def process(self):
        """Process the command"""
        # No command specified
        if len(self.raw_message_lst) == 0:
            await self._show_help()
            return

        # Parse the raw message into self.command & self.args
        self.command = self.raw_message_lst[0]

        # If arguments were given
        if len(self.raw_message_lst) > 1:
            self.args = self.raw_message_lst[1:]

        if not self.is_admin:
            await self._bad_perms()
            return

        # Query matrix for members in this room
        raw_members: JoinedMembersResponse | JoinedMembersError = (
            await self.client.joined_members(self.room.room_id)
        )

        if isinstance(raw_members, JoinedMembersError):
            # TODO: Probably better way to handle this error?
            logger.error(f"Could not get room members for room {self.room.room_id}")

        self.members = [i.user_id for i in raw_members.members]

        match self.command:
            case "help":
                await self._show_help()
            case "threads":
                await self.toggle_hide_in_threads()
            case "personality":
                await self._personality()
            case "subscribe":
                await self._add_rss_feed()
            case "unsubscribe":
                await self._remove_rss_feed()
            case "feeds":
                await self._list_rss_feeds()
            case "add":
                await self._add_admin()
            case "remove":
                await self._remove_admin()
            case "admins":
                await self._list_admins()
            case "interject":
                await self._interject()
            # You must be a super admin to set the greeting.
            case "greeting" if self.event.sender not in g.config.admins:
                await self._bad_perms()
            case "greeting":
                await self._greeting()
            case _:
                await self._show_help()

    async def _bad_perms(self) -> None:
        """Tell the user they don't have permission to use a command."""
        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Sorry {id_to_username(self.event.sender)}, you don't have permission to use this command!",
            notice=True,
        )

    async def _show_help(self) -> None:
        """Show the help text"""
        await send_text_to_room(
            self.client,
            self.room.room_id,
            g.help_text,
            notice=True,
        )

    async def _unknown_command(self) -> None:
        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Unknown command '{self.command}'. Try the 'help' command for more information.",
            notice=True,
        )

    async def _greeting(self) -> None:
        """Set a new greeting or print the current one."""
        if self.args:
            g.config.greeting = " ".join(self.args)
            self.store.set_greeting(g.config.greeting)
            await send_text_to_room(
                self.client, self.room.room_id, "New greeting set!", notice=True
            )
        else:
            await send_text_to_room(
                self.client, self.room.room_id, self.store.get_greeting(), notice=True
            )

    async def toggle_hide_in_threads(self) -> None:
        """Toggle the use of threads to hide some of the automated bot's responses."""
        hiding: bool = self.store.toggle_hide_in_threads(self.room.room_id)

        if hiding:
            msg = "Now hiding automated bot responses in threads."
        else:
            msg = "No longer hiding automated bot responses in threads."

        await send_text_to_room(self.client, self.room.room_id, msg, notice=True)

    async def _add_admin(self) -> None:
        """Add an admin to the room."""
        # Show help if no arguments were supplied
        if not self.args:
            await self._show_help()
            return

        new_admin: str = self.args[0]

        # Check if the user_id we are making an admin is in this room
        if new_admin not in self.members:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"User {new_admin} is not in this room!",
                notice=True,
            )
            return

        self.store.set_room_admin(self.room.room_id, new_admin)

        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"{new_admin} is now an admin in this room!",
            notice=True,
        )

    async def _remove_admin(self) -> None:
        """Remove an admin from the room."""
        # Show help if no arguments were supplied
        if not self.args:
            await self._show_help()
            return

        admin_id = self.args[0]

        room_admins = self.store.list_room_admins(self.room.room_id)

        # If the user ID is not an admin in this room
        if admin_id not in room_admins:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"{admin_id} is not an admin in this room!",
                notice=True,
            )
            return

        # If there is only one admin in this room
        if len(room_admins) == 1:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"You are the only admin in this room, and cannot be removed.",
                notice=True,
            )
            return

        # If the user ID is not in this room.
        if admin_id not in self.members:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"{admin_id} is a member of this room!",
                notice=True,
            )
            return

        # Disallow removing yourself from admin list
        if admin_id == self.event.sender:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                "You cannot revoke your own admin permissions!",
                notice=True,
            )
            return

        self.store.remove_room_admin(self.room.room_id, admin_id)

        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"{admin_id} is no longer an admin in this room.",
            notice=True,
        )

    async def _list_admins(self):
        """Send a list of all admins in this room."""

        admins: str = " ".join(self.store.list_room_admins(self.room.room_id))

        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Admins in this room: {admins}",
            notice=True,
        )

    async def _list_rss_feeds(self):
        """Send a list of RSS feeds this room is subscribed to."""
        feeds: str = "\n".join(self.store.get_feeds_from_room(self.room.room_id))

        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"RSS subscriptions:\n{feeds}",
            markdown_convert=False,
            notice=True,
        )

    async def _add_rss_feed(self):
        """Subscribe this room to an RSS feed"""
        if not self.args:
            await self._show_help()
            return

        url = self.args[0].strip()

        subscribed_feeds = self.store.get_feeds_from_room(self.room.room_id)

        if url in subscribed_feeds:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                "The room is already subscribed to this RSS feed!",
                notice=True,
            )
            return

        if not validate_rss_url(self.args[0]):
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"'{url}' is not a valid RSS feed.",
                notice=True,
            )
            return

        self.store.add_rss_feed(self.room.room_id, url)

        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Subscribed to {url}! I'll send new updates to the room.",
            notice=True,
        )

    async def _remove_rss_feed(self):
        """Unsubscribe this room from an RSS feed."""
        if not self.args:
            await self._show_help()
            return

        url = self.args[0].strip()

        if url not in self.store.get_feeds_from_room(self.room.room_id):
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"This room is not subscribed to {url}.",
                notice=True,
            )
            return

        self.store.remove_rss_feed(self.room.room_id, url)

        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Unsubscribed from {url}.",
            notice=True,
        )

    async def _personality(self):
        if not self.args:
            personality = self.store.get_personality(self.room.room_id)

            if not personality:
                personality = g.config.original_prompt

            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"Current personality:\n{personality}",
                markdown_convert=False,
                notice=True,
            )
            return

        personality = " ".join(self.args)
        self.store.set_personality(self.room.room_id, personality)

        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"New Personality:\n{personality}",
            markdown_convert=False,
            notice=True,
        )

    async def _interject(self):
        if not self.args:
            status_msg = ""
            percentage = self.store.get_interject(self.room.room_id)
            # Avoid 'ZeroDivisionError'
            if percentage == 0:
                status_msg = "Interjecting disabled (odds set to 0)"
            else:
                odds = round(1 / percentage)
                status_msg = f"Interjecting every ~{odds} messages"

            await send_text_to_room(
                self.client,
                self.room.room_id,
                status_msg,
                markdown_convert=False,
                notice=True,
            )
            return

        odds = self.args[0]

        try:
            odds = int(odds)
        except (TypeError, AssertionError):
            await send_text_to_room(
                self.client,
                self.room.room_id,
                "Supplied odds must be a positive integer",
                notice=True,
            )
            return

        if odds < 0 or odds > 10000:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                "Odds must be between 0-10000. To disable interjecting set odds to 0",
                notice=True,
            )
            return

        # Avoid ZeroDivisionError
        percentage = 0.00
        status_msg = "Interjecting disabled"

        if odds != 0:
            percentage = 1 / odds
            status_msg = f"Now interjecting every ~{odds} messages"

        self.store.set_interject(self.room.room_id, percentage)

        await send_text_to_room(self.client, self.room.room_id, status_msg, notice=True)
