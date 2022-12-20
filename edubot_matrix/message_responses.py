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
from random import random

from nio import AsyncClient, MatrixRoom, RoomMessagesError, RoomMessageText

from edubot_matrix import g
from edubot_matrix.config import Config
from edubot_matrix.storage import Storage
from edubot_matrix.utils import (
    convert_room_messages_to_dict,
    id_to_username,
    send_text_to_room,
)

logger = logging.getLogger(__name__)


class Message:
    def __init__(
        self,
        client: AsyncClient,
        store: Storage,
        config: Config,
        message_content: str,
        room: MatrixRoom,
        event: RoomMessageText,
    ):
        """Initialize a new Message

        Args:
            client: nio client used to interact with edubot_matrix.

            store: Bot storage.

            config: Bot configuration parameters.

            message_content: The body of the message.

            room: The room the event came from.

            event: The event defining the message.
        """
        self.client = client
        self.store = store
        self.config = config
        self.message_content = message_content
        self.room = room
        self.event = event

    async def process(self) -> None:
        """Process and possibly respond to the message"""
        if self._check_if_response():
            await self._respond()

    def _check_if_response(self):
        if (
            id_to_username(self.config.user_id) in self.message_content.lower()
            or random() < 0.05
            or self.room.member_count <= 2
        ):
            return True

        return False

    async def _respond(self):
        """Respond to a message using a GPT completion."""
        # If in a DM or if mentioned, read more events.
        # Why? The bot can afford to respond a bit slower if it wasn't mentioned.
        # However, when the bot is mentioned, quicker replies are preferred over more context.
        limit = 20
        if (
            id_to_username(g.config.user_id) not in self.message_content.lower()
            or self.room.member_count <= 2
        ):
            limit = 40

        # The method is called 'room_messages' but it actually returns all events in the room.
        events = await self.client.room_messages(
            self.room.room_id,
            self.client.next_batch,
            limit=limit,
        )

        if isinstance(events, RoomMessagesError):
            logger.error(f"Could not read room of id: {self.room.room_id}")
            return

        # HACK: message_filter kwarg in room_messages method doesn't work in DMS when filtering only m.room.message
        # So we have to get all the events and extract message events with Python.
        events.chunk = [i for i in events.chunk if isinstance(i, RoomMessageText)]

        # Convert the message events into the format required by edubot lib
        context = convert_room_messages_to_dict(events)

        # Get the GPT completion and use the custom room personality if it exists
        if personality := self.store.get_personality(self.room.room_id):
            completion = g.edubot.gpt_answer(context, events.room_id, personality)
        else:
            completion = g.edubot.gpt_answer(context, events.room_id)

        await send_text_to_room(
            self.client, self.room.room_id, completion, markdown_convert=False
        )
