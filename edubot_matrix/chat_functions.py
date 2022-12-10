import logging
from datetime import datetime
from typing import Optional, Union

from edubot.types import MessageInfo
from markdown import markdown
from nio import (
    AsyncClient,
    ErrorResponse,
    MatrixRoom,
    MegolmEvent,
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
    reply_to_event_id: Optional[str] = None,
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
    messages: RoomMessagesResponse,
) -> list[dict[str, Union[str, datetime]]]:
    """
    Convert list of events into the format required by EduBot lib.
    """
    # Remove bad events from the list
    messages_lst = [i for i in messages.chunk if isinstance(i, RoomMessageText)]

    result_lst: list[MessageInfo] = []

    for event in reversed(messages_lst):
        result_lst.append(
            {
                "username": id_to_username(event.sender),
                "message": event.body,
                "time": ms_to_datetime(event.server_timestamp),
            }
        )

    return result_lst


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
