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
import re
import tempfile
from random import random

import aiofiles.os
from nio import (
    AsyncClient,
    MatrixRoom,
    RoomMessagesError,
    RoomMessageText,
    UploadResponse,
)

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
        if search := re.search(g.IMAGEGEN_REGEX, self.message_content):
            await self._respond_image(search.group(4))

        elif self._check_if_response():
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

    async def _respond_image(self, prompt) -> None:
        """

        Args:
            prompt:
        """
        img = g.edubot.generate_image(prompt)

        if img is None:
            await send_text_to_room(
                self.client,
                self.room.room_id,
                "Sorry this prompt contains inappropriate content.",
            )
            return

        f = tempfile.NamedTemporaryFile()
        img.save(f, format="png")

        (width, height) = img.size

        file_stat = await aiofiles.os.stat(f.name)
        async with aiofiles.open(f.name, "r+b") as async_f:
            # noinspection PyTypeChecker
            # 'async_f' var is incorrectly shown as being the incorrect type
            resp, decryption_keys = await self.client.upload(
                async_f,
                content_type="image/png",
                filesize=file_stat.st_size,
                encrypt=True,
            )
            # The temp file is automatically deleted here, because the context manager closes it

        if not isinstance(resp, UploadResponse):
            logger.error(
                f"Failed to upload generated image to server for room {self.room.room_id}"
            )
            await send_text_to_room(
                self.client,
                self.room.room_id,
                "Sorry, I encountered an error when uploading the image I generated.",
            )
            return

        content = {
            "body": f"An image of {prompt}",
            "info": {
                "size": file_stat.st_size,
                "mimetype": "image/png",
                "thumbnail_info": None,
                "w": width,
                "h": height,
                "thumbnail_url": None,
            },
            "msgtype": "m.image",
            "file": {
                "url": resp.content_uri,
                "key": decryption_keys["key"],
                "iv": decryption_keys["iv"],
                "hashes": decryption_keys["hashes"],
                "v": decryption_keys["v"],
            },
        }

        try:
            await self.client.room_send(
                self.room.room_id, message_type="m.room.message", content=content
            )
            logger.info(f"Image sent to room {self.room.room_id}")
        except Exception:
            logger.error(f"Image couldn't be sent to room {self.room.room_id}")
