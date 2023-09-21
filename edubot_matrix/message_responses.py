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
import io
import logging
import re
import tempfile
from random import random

import aiofiles.os
import PIL
from edubot.types import ImageInfo, MessageInfo
from nio import (
    AsyncClient,
    DownloadError,
    ErrorResponse,
    MatrixRoom,
    RoomMessageImage,
    RoomMessagesError,
    RoomMessageText,
    UploadResponse,
)
from urlextract import URLExtract

from edubot_matrix import g
from edubot_matrix.config import Config
from edubot_matrix.storage import Storage
from edubot_matrix.utils import (
    convert_room_messages_to_dict,
    id_to_username,
    ms_to_datetime,
    send_text_to_room,
)

logger = logging.getLogger(__name__)

extractor = URLExtract()
extractor.update()


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
        if type(self.event) is RoomMessageImage:
            await self._process_image()
            return

        # Remove quotes from messages so that URLS in replies don't get summarised
        message_content_no_quotes = ""
        for line in self.message_content.split("\n"):
            if not line.startswith(">"):
                message_content_no_quotes += line + "\n"

        # Check if there are any urls in the message
        urls = extractor.find_urls(message_content_no_quotes)

        if urls:
            # TODO: only summarising the first URL right now
            summary = g.edubot.summarise_url(
                urls[0],
                MessageInfo(
                    username=self.event.sender,
                    message=self.message_content,
                    time=ms_to_datetime(self.event.server_timestamp),
                ),
                self.room.room_id,
            )
            if summary:
                thread_reply_id = None
                if self.store.get_hide_in_threads(room_id=self.room.room_id):
                    thread_reply_id = self.event.event_id

                await send_text_to_room(
                    self.client,
                    self.room.room_id,
                    summary,
                    markdown_convert=False,
                    notice=True,
                    thread_reply_to_event_id=thread_reply_id,
                )

        bot_mentioned_or_dm = (
            id_to_username(self.config.user_id) in self.message_content.lower()
            or self.room.member_count <= 2
        )
        if (
            search := re.search(g.IMAGEGEN_REGEX, self.message_content)
        ) and bot_mentioned_or_dm:
            await self._respond_image(search.group(3))

        elif bot_mentioned_or_dm or random() < self.store.get_interject(
            self.room.room_id
        ):
            await self._respond()

    async def _process_image(self):
        """Save images to edubot DB"""
        download_resp = await self.client.download(self.event.url)

        if type(download_resp) is DownloadError:
            logger.error(f"Could not download image: {self.event.url}")
            return

        image_data = io.BytesIO(download_resp.body)

        image: ImageInfo = {
            "username": self.event.sender,
            "image": PIL.Image.open(image_data),
            "time": ms_to_datetime(self.event.server_timestamp),
        }
        g.edubot.save_image_to_context(image, self.room.room_id)

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

        # If GPT fails for whatever reason it's better to not respond rather than send an empty string
        if completion is None:
            return

        await send_text_to_room(
            self.client, self.room.room_id, completion, markdown_convert=False
        )

    async def _respond_image(self, prompt) -> None:
        """
        Respond to a message using an AI generated image
        """
        img = g.edubot.generate_image(
            prompt,
            convert_room_messages_to_dict(self.event),
            thread_name=self.room.room_id,
        )

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

        resp = await self.client.room_send(
            self.room.room_id, message_type="m.room.message", content=content
        )

        if type(resp) is ErrorResponse:
            logger.error(f"Image couldn't be sent to room {self.room.room_id}")
            return

        logger.info(f"Image sent to room {self.room.room_id}")
