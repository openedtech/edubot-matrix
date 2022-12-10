from nio import AsyncClient, MatrixRoom, RoomMessageText

from edubot_matrix import g
from edubot_matrix.chat_functions import send_text_to_room, id_to_username
from edubot_matrix.config import Config
from edubot_matrix.storage import Storage


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
        self.is_admin = store.check_if_admin(self.event.sender, self.room.room_id)
        self.raw_message_lst: list[str] = command_and_args.split(" ")

        self.command = ""
        self.args: list[str] = []

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

        if self.command == "help":
            await self._show_help()
            return

        if self.is_admin:
            if self.command == "add":
                await self._add_admin()
            elif self.command == "remove":
                await self._remove_admin()
            elif self.command == "admins":
                await self._list_admins()
            # You must be a super admin to set the greeting.
            elif self.command == "greeting" and self.event.sender in g.config.admins:
                await self._greeting()
        else:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                f"Sorry {id_to_username(self.event.sender)}, you don't have permission to use this command!"
            )


    async def _show_help(self) -> None:
        """Show the help text"""
        await send_text_to_room(
            self.client,
            self.room.room_id,
            (
                f"#Room Admin commands:\n"
                f"`{g.config.command_prefix} rss` Manage RSS feeds.\n"
                f"`{g.config.command_prefix} add [user_id]` make a user an admin in this room.\n"
                f"`{g.config.command_prefix} remove [user_id]` revoke a user's admin rights in this room.\n"
                f"`{g.config.command_prefix} admins` list who is an admin in this room.\n"
                
                f"#Super Admin commands:"
                f"`{g.config.command_prefix} greeting [msg]` change greeting, if no msg is supplied the "
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
        if len(self.args) >= 2:
            g.config.greeting = " ".join(self.args)
            with open("GREETING", "w") as f:
                f.write(g.config.greeting)
            await send_text_to_room(self.client, self.room.room_id, "New greeting set!")
        else:
            await send_text_to_room(self.client, self.room.room_id, f"{g.config.greeting)

    async def _add_admin(self) -> None:
        """
        Add an admin to this room
        """
        self.store.add_room_admin(self., self.room.room_id)

        await send_text_to_room(
            self.client,
            self.room.room_id,
            ""
        )

    def _remove_admin(self) -> None:
        """
        Remove an admin from this room
        Returns:

        """

        if len(self.args)

    async def _list_admins(self):
        pass
