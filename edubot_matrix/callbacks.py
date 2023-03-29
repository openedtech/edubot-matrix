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

import asyncio
import logging

from edubot.types import CompletionInfo
from nio import (
    AsyncClient,
    InviteMemberEvent,
    JoinError,
    MatrixRoom,
    RoomGetEventError,
    RoomMessageText,
    UnknownEvent,
)

from edubot_matrix import g
from edubot_matrix.bot_commands import Command
from edubot_matrix.config import Config
from edubot_matrix.g import NEGATIVE_EMOJIS, POSITIVE_EMOJIS
from edubot_matrix.message_responses import Message
from edubot_matrix.storage import Storage
from edubot_matrix.utils import ms_to_datetime, send_text_to_room

logger = logging.getLogger(__name__)


class Callbacks:
    def __init__(self, client: AsyncClient, store: Storage, config: Config):
        """
        Args:
            client: nio client used to interact with matrix.

            store: Bot storage.

            config: Bot configuration parameters.
        """
        self.client = client
        self.store = store
        self.config = config
        self.command_prefix = g.config.command_prefix

    async def message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        """Callback for when a message event is received

        Args:
            room: The room the event came from.

            event: The event defining the message.
        """
        # Extract the message text
        msg = event.body

        # Ignore messages from ourselves
        if event.sender == self.client.user:
            return

        logger.debug(
            f"Bot message received for room {room.display_name} | "
            f"{room.user_name(event.sender)}: {msg}"
        )

        # Ignore messages in threads and edits
        # TODO: Handle threads properly instead of ignoring
        rel_type = (
            event.source.get("content", {}).get("m.relates_to", {}).get("rel_type")
        )
        if rel_type in ("m.thread", "m.replace"):
            logger.debug(
                f"Ignoring '{event.event_id}' in '{room.display_name}': rel_type = {rel_type}."
            )
            return

        # Process as message if in a public room without command prefix
        has_command_prefix = msg.startswith(self.command_prefix)

        if not has_command_prefix:
            # General message listener
            message = Message(self.client, self.store, self.config, msg, room, event)
            await message.process()
            return

        # Admin commands
        if has_command_prefix:
            # Remove the command prefix
            msg = msg.replace(self.command_prefix, "", 1).lstrip()

        command = Command(self.client, self.store, self.config, msg, room, event)
        await command.process()

    async def _join_message(self, room_id):
        """Send greeting to room when we join."""
        # Wait to allow time for the bot to join the room
        await asyncio.sleep(3)
        await send_text_to_room(self.client, room_id, g.config.greeting)

    async def invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        """Callback for when an invite is received. Join the room specified in the invite.

        Args:
            room: The room that we are invited to.

            event: The invite event.
        """
        logger.debug(f"Got invite to {room.room_id} from {event.sender}.")

        # Attempt to join 3 times before giving up
        for attempt in range(3):
            result = await self.client.join(room.room_id)
            if type(result) == JoinError:
                logger.error(
                    f"Error joining room {room.room_id} (attempt %d): %s",
                    attempt,
                    result.message,
                )
            else:
                break
        else:
            logger.error("Unable to join room: %s", room.room_id)

        # Send bot greeting to the room in the near future
        asyncio.ensure_future(self._join_message(room.room_id))

        # The user who invited the bot and the room creator should be made admins.
        self.store.set_room_admin(room.room_id, event.sender)

        # room.creator is sometimes an empty string
        if room.creator and room.creator != event.sender:
            self.store.set_room_admin(room.room_id, room.creator)

        # Successfully joined room
        logger.info(f"Joined {room.room_id}")

    async def invite_event_filtered_callback(
        self, room: MatrixRoom, event: InviteMemberEvent
    ) -> None:
        """
        Since the InviteMemberEvent is fired for every m.room.member state received
        in a sync response's `rooms.invite` section, we will receive some that are
        not actually our own invite event (such as the inviter's membership).
        This makes sure we only call `callbacks.invite` with our own invite events.
        """
        if event.state_key == self.client.user_id:
            # This is our own membership (invite) event
            await self.invite(room, event)

    async def _reaction(
        self, room: MatrixRoom, event: UnknownEvent, reacted_to_id: str
    ) -> None:
        """A reaction was sent to one of our messages. Let's send a reply acknowledging it.
        Args:
            room: The room the reaction was sent in.
            event: The reaction event.
            reacted_to_id: The event ID that the reaction points to.
        """
        logger.debug(f"Got reaction to {room.room_id} from {event.sender}.")

        # Get the original event that was reacted to
        event_response = await self.client.room_get_event(room.room_id, reacted_to_id)
        if isinstance(event_response, RoomGetEventError):
            logger.warning(
                "Error getting event that was reacted to (%s)", reacted_to_id
            )
            return

        original_event = event_response.event

        # Only acknowledge reactions to events that we sent
        if original_event.sender != self.config.user_id:
            return

        # Only acknowledge reactions to text
        if not isinstance(original_event, RoomMessageText):
            return

        emoji = event.source["content"]["m.relates_to"]["key"]

        # Get rid of skin tone character if it exists
        emoji = emoji[0]

        offset = 0
        if emoji in POSITIVE_EMOJIS:
            offset = 1
        elif emoji in NEGATIVE_EMOJIS:
            offset = -1

        if offset != 0:
            # TODO: Is there a way to get redacted reaction events? Currently people can spam reaction events to get
            #  infinite votes.
            completion: CompletionInfo = {
                "message": original_event.body,
                "time": ms_to_datetime(original_event.server_timestamp),
            }
            g.edubot.change_completion_score(offset, completion, room.room_id)

    async def unknown(self, room: MatrixRoom, event: UnknownEvent) -> None:
        """Callback for when an event with a type that is unknown to matrix-nio is received.
        Currently, this is used for reaction events, which are not yet part of a released
        matrix spec (and are thus unknown to nio).
        Args:
            room: The room the reaction was sent in.
            event: The event itself.
        """
        if event.type == "m.reaction":
            # Get the ID of the event this was a reaction to
            relation_dict = event.source.get("content", {}).get("m.relates_to", {})

            reacted_to = relation_dict.get("event_id")
            if reacted_to and relation_dict.get("rel_type") == "m.annotation":
                await self._reaction(room, event, reacted_to)
                return

        logger.debug(
            f"Got unknown event with type to {event.type} from {event.sender} in {room.room_id}."
        )
