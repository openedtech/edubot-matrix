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
        )

    async def _show_help(self) -> None:
        """Show the help text"""
        await send_text_to_room(
            self.client,
            self.room.room_id,
            (
                f"#Room Admin commands:"
                f"`{g.config.command_prefix} subscribe` Subscribe to an RSS feed.\n\n"
                f"`{g.config.command_prefix} unsubscribe` Unsubscribe from an RSS feed.\n\n"
                f"`{g.config.command_prefix} feeds` List subscribed RSS feeds.\n\n"
                f"`{g.config.command_prefix} add user_id` Make a user an admin in this room.\n\n"
                f"`{g.config.command_prefix} remove user_id` Revoke a user's admin rights in this room.\n\n"
                f"`{g.config.command_prefix} admins` List who is an admin in this room.\n\n"
                f"#Super Admin commands:\n"
                f"`{g.config.command_prefix} greeting [msg]` Change the bot's greeting, if no msg is supplied the "
                f"current greeting is shown.\n"
            ),
        )

    async def _unknown_command(self) -> None:
        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Unknown command '{self.command}'. Try the 'help' command for more information.",
        )

    async def _greeting(self) -> None:
        """Set a new greeting or print the current one."""
        if self.args:
            g.config.greeting = " ".join(self.args)
            with open("GREETING", "w") as f:
                f.write(g.config.greeting)
            await send_text_to_room(self.client, self.room.room_id, "New greeting set!")
        else:
            await send_text_to_room(self.client, self.room.room_id, g.config.greeting)

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
                self.client, self.room.room_id, f"User {new_admin} is not in this room!"
            )
            return

        self.store.add_room_admin(self.room.room_id, new_admin)

        await send_text_to_room(
            self.client, self.room.room_id, f"{new_admin} is now an admin in this room!"
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
            )
            return

        # If there is only one admin in this room
        if len(room_admins) == 1:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"You are the only admin in this room, and cannot be removed.",
            )
            return

        # If the user ID is not in this room.
        if admin_id not in self.members:
            await send_text_to_room(
                self.client, self.room.room_id, f"{admin_id} is a member of this room!"
            )
            return

        # Disallow removing yourself from admin list
        if admin_id == self.event.sender:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                "You cannot revoke your own admin permissions!",
            )
            return

        self.store.remove_room_admin(self.room.room_id, admin_id)

        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"{admin_id} is no longer an admin in this room.",
        )

    async def _list_admins(self):
        """Send a list of all admins in this room."""

        admins: str = " ".join(self.store.list_room_admins(self.room.room_id))

        await send_text_to_room(
            self.client, self.room.room_id, f"Admins in this room: {admins}"
        )

    async def _list_rss_feeds(self):
        """Send a list of RSS feeds this room is subscribed to."""
        feeds: str = "\n".join(self.store.get_room_subscriptions(self.room.room_id))

        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"RSS subscriptions:\n{feeds}",
            markdown_convert=False,
        )

    async def _add_rss_feed(self):
        """Subscribe this room to an RSS feed"""
        if not self.args:
            await self._show_help()
            return

        url = self.args[0].strip()

        subscribed_feeds = self.store.get_room_subscriptions(self.room.room_id)

        if url in subscribed_feeds:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                "The room is already subscribed to this RSS feed!",
            )
            return

        if not validate_rss_url(self.args[0]):
            await send_text_to_room(
                self.client, self.room.room_id, f"'{url}' is not a valid RSS feed."
            )
            return

        self.store.add_rss_feed(self.room.room_id, url)

        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Subscribed to {url}! I'll send new updates to the room.",
        )

    async def _remove_rss_feed(self):
        """Unsubscribe this room from an RSS feed."""
        if not self.args:
            await self._show_help()
            return

        url = self.args[0].strip()

        if url not in self.store.get_room_subscriptions(self.room.room_id):
            await send_text_to_room(
                self.client, self.room.room_id, f"This room is not subscribed to {url}."
            )
            return

        self.store.remove_rss_feed(self.room.room_id, url)

        await send_text_to_room(
            self.client, self.room.room_id, f"Unsubscribed from {url}."
        )
