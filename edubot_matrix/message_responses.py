import logging
from random import random

from nio import AsyncClient, MatrixRoom, RoomMessageText, RoomMessagesError

from edubot_matrix import g
from edubot_matrix.chat_functions import send_text_to_room, convert_room_messages_to_dict, ms_to_datetime, \
    id_to_username
from edubot_matrix.config import Config
from edubot_matrix.storage import Storage

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
        if self.room.member_count <= 2:
            return True

        if self.config.user_id in self.message_content.lower() or random() < 0.05:
            return True

        return False

    async def _respond(self):
        limit = 20
        breakpoint()
        if id_to_username(g.config.user_id) not in self.message_content.lower() or self.room.member_count <= 2:
            limit = 60

        messages = await self.client.room_messages(self.room.room_id, self.client.loaded_sync_token, limit=limit)

        # TODO: Why does this fire on encrypted rooms sometimes even though the room can be read?
        #if isinstance(messages, RoomMessagesError):
            #logger.error(f"Could not read room of id: {self.room.room_id}")

        context = convert_room_messages_to_dict(messages)
        message_dict = {
            "username": id_to_username(self.event.sender),
            "message": self.message_content,
            "time": ms_to_datetime(self.event.server_timestamp),
        }
        context.append(message_dict)

        response = g.edubot.gpt_answer(context, messages.room_id)

        await send_text_to_room(self.client, self.room.room_id, response, markdown_convert=False)
