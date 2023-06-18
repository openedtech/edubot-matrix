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
"""
Small helper functions for formatting and common chat tasks
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Union

from edubot.types import MessageInfo
from markdown import markdown
from nio import (
    AsyncClient,
    ErrorResponse,
    MatrixRoom,
    MegolmEvent,
    RoomMessageNotice,
    RoomMessagesResponse,
    RoomMessageText,
    RoomSendResponse,
    SendRetryError,
)

logger = logging.getLogger(__name__)


async def send_text_to_room(
    client: AsyncClient,
    room_id: str,
    message: str,
    notice: bool = False,
    markdown_convert: bool = True,
    thread_reply_to_event_id: Optional[str] = None,
) -> Union[RoomSendResponse, ErrorResponse]:
    """Send text to a matrix room.

    Args:
        client: The client to communicate to matrix with.

        room_id: The ID of the room to send the message to.

        message: The message content.

        notice: Whether the message should be sent with an "m.notice" message type
            (will not ping users).

        markdown_convert: Whether to convert the message content to markdown.
            Defaults to true.

        thread_reply_to_event_id: Whether this message is a thread reply to another event. The event
            ID this is message is a reply to.

    Returns:
        A RoomSendResponse if the request was successful, else an ErrorResponse.
    """
    # Determine whether to ping room members or not
    msgtype = "m.notice" if notice else "m.text"

    content = {
        "msgtype": msgtype,
        "body": message,
    }

    if markdown_convert:
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = markdown(message)

    if thread_reply_to_event_id:
        content["m.relates_to"] = {
            "rel_type": "m.thread",
            "event_id": thread_reply_to_event_id,
            # Fallback for clients not supporting threads
            "is_falling_back": "true",
            "m.in_reply_to": {"event_id": thread_reply_to_event_id},
        }

    try:
        return await client.room_send(
            room_id,
            "m.room.message",
            content,
            ignore_unverified_devices=True,
        )
    except SendRetryError:
        logger.exception(f"Unable to send message response to {room_id}")


async def send_image_to_room(
    client: AsyncClient,
    room_id: str,
    image_bytes: str,
    notice: bool = False,
    markdown_convert: bool = True,
    reply_to_event_id: Optional[str] = None,
) -> Union[RoomSendResponse, ErrorResponse]:
    """Send an image to a matrix room.

    Args:
        client: The client to communicate to matrix with.

        room_id: The ID of the room to send the message to.

        message: The message content.

        notice: Whether the message should be sent with an "m.notice" message type
            (will not ping users).

        markdown_convert: Whether to convert the message content to markdown.
            Defaults to true.

        reply_to_event_id: Whether this message is a reply to another event. The event
            ID this is message is a reply to.

    Returns:
        A RoomSendResponse if the request was successful, else an ErrorResponse.
    """
    # Determine whether to ping room members or not
    msgtype = "m.notice" if notice else "m.text"

    content = {
        "msgtype": msgtype,
        "body": message,
    }

    if markdown_convert:
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = markdown(message)

    if reply_to_event_id:
        content["m.relates_to"] = {"m.in_reply_to": {"event_id": reply_to_event_id}}

    try:
        return await client.room_send(
            room_id,
            "m.room.message",
            content,
            ignore_unverified_devices=True,
        )
    except SendRetryError:
        logger.exception(f"Unable to send message response to {room_id}")


def make_pill(user_id: str, displayname: str = None) -> str:
    """Convert a user ID (and optionally a display name) to a formatted user 'pill'

    Args:
        user_id: The MXID of the user.

        displayname: An optional displayname. Clients like Element will figure out the
            correct display name no matter what, but other clients may not. If not
            provided, the MXID will be used instead.

    Returns:
        The formatted user pill.
    """
    if not displayname:
        # Use the user ID as the displayname if not provided
        displayname = user_id

    return f'<a href="https://matrix.to/#/{user_id}">{displayname}</a>'


def id_to_username(user_id: str) -> str:
    return user_id.split(":")[0].replace("@", "")


def ms_to_datetime(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp / 1000)


def convert_room_messages_to_dict(
    messages: RoomMessagesResponse | RoomMessageText,
) -> list[MessageInfo] | MessageInfo:
    """
    Convert list of events, or one event into the format required by EduBot lib.
    """
    if type(messages) is RoomMessagesResponse:
        # Remove bad events from the list
        messages_lst = [
            i
            for i in messages.chunk
            if isinstance(i, RoomMessageText) or isinstance(i, RoomMessageNotice)
        ]
    else:
        messages_lst = [messages]

    result_lst: list[MessageInfo] = []

    for event in reversed(messages_lst):
        result_lst.append(
            {
                "username": id_to_username(event.sender),
                "message": event.body,
                "time": ms_to_datetime(event.server_timestamp),
            }
        )

    if len(result_lst) > 1:
        return result_lst

    return result_lst[0]


def unix_utc() -> int:
    """
    Get the UTC Unix timestamp in seconds.
    """
    return round(datetime.now(timezone.utc).timestamp())


def validate_user_id(user_id: str):
    """
    Checks if a user_id is in the valid format
    Args:
        user_id:

    Returns:

    """
    pass


async def decryption_failure(self, room: MatrixRoom, event: MegolmEvent) -> None:
    """Callback for when an event fails to decrypt. Inform the user"""
    logger.error(
        f"Failed to decrypt event '{event.event_id}' in room '{room.room_id}'!"
        f"\n\n"
        f"Tip: try using a different device ID in your config file and restart."
        f"\n\n"
        f"If all else fails, delete your store directory and let the bot recreate "
        f"it (your reminders will NOT be deleted, but the bot may respond to existing "
        f"commands a second time)."
    )

    user_msg = (
        "Unable to decrypt this message. "
        "Check whether you've chosen to only encrypt to trusted devices."
    )

    await send_text_to_room(
        self.client,
        room.room_id,
        user_msg,
        reply_to_event_id=event.event_id,
    )
