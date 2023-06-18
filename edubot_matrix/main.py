#!/usr/bin/env python3
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
import sys
from time import sleep

from aiohttp import ClientConnectionError, ServerDisconnectedError
from edubot.bot import EduBot
from nio import (
    AsyncClient,
    AsyncClientConfig,
    InviteMemberEvent,
    LocalProtocolError,
    LoginError,
    RoomMessageImage,
    RoomMessageText,
    UnknownEvent,
)

from edubot_matrix import g
from edubot_matrix.callbacks import Callbacks
from edubot_matrix.config import Config
from edubot_matrix.rss import sync_rss_feeds
from edubot_matrix.storage import Storage
from edubot_matrix.utils import id_to_username

logger = logging.getLogger(__name__)


async def main():
    """The first function that is run when starting the bot"""

    # Read user-configured options from a config file.
    # A different config file path can be specified as the first command line argument
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "edubot_matrix/config.yaml"

    # Read the parsed config file and create a Config object
    config = Config(config_path)

    # Allow the config to be imported anywhere
    # TODO: Maybe there is a better way to do this
    g.config = config

    # Add some config fields that are not used by the nio lib
    g.config.bot_name = id_to_username(config.user_id)
    g.config.command_prefix = f"!{g.config.bot_name}"

    g.help_text = (
        f"#Room Admin commands:\n"
        f"`{g.config.command_prefix} personality [new personality]` Change or print the personality of the "
        f"bot.\n\n "
        f"`{g.config.command_prefix} subscribe {{url}}` Subscribe to an RSS feed.\n\n"
        f"`{g.config.command_prefix} unsubscribe` Unsubscribe from an RSS feed.\n\n"
        f"`{g.config.command_prefix} feeds` List subscribed RSS feeds.\n\n"
        f"`{g.config.command_prefix} interject [odds]` Change or print interject odds (the average amount of "
        f"messages between random interjections). Set to 0 to disable interjections.\n\n"
        f"`{g.config.command_prefix} threads` Toggle the use of threads to hide some of the bot's automated responses.\n\n"
        f"`{g.config.command_prefix} add {{user_id}}` Make a user an admin in this room.\n\n"
        f"`{g.config.command_prefix} remove {{user_id}}` Revoke a user's admin rights in this room.\n\n"
        f"`{g.config.command_prefix} admins` List who is an admin in this room.\n\n"
        f"#Super Admin commands:\n"
        f"`{g.config.command_prefix} greeting [msg]` Change the bot's greeting, if no msg is supplied the "
        f"current greeting is shown.\n"
    )

    g.edubot = EduBot(
        g.config.bot_name, "matrix", [config.original_prompt, g.help_text]
    )

    # Configure the database
    store = Storage(config.database)

    g.config.greeting = store.get_greeting()

    # Configuration options for the AsyncClient
    client_config = AsyncClientConfig(
        max_limit_exceeded=0,
        max_timeouts=0,
        store_sync_tokens=True,
        encryption_enabled=True,
    )

    # Initialize the matrix client
    client = AsyncClient(
        config.homeserver_url,
        config.user_id,
        device_id=config.device_id,
        store_path=config.store_path,
        config=client_config,
    )

    if config.user_token:
        client.access_token = config.user_token
        client.user_id = config.user_id

    # Set up event callbacks
    callbacks = Callbacks(client, store, config)
    client.add_event_callback(callbacks.message, (RoomMessageText, RoomMessageImage))
    client.add_event_callback(
        callbacks.invite_event_filtered_callback, (InviteMemberEvent,)
    )
    client.add_event_callback(callbacks.unknown, UnknownEvent)

    asyncio.create_task(sync_rss_feeds(client, store))

    # Keep trying to reconnect on failure (with some time in-between)
    while True:
        try:
            if config.user_token:
                # Use token to log in
                client.load_store()

                # Sync encryption keys with the server
                if client.should_upload_keys:
                    await client.keys_upload()
            else:
                # Try to login with the configured username/password
                try:
                    login_response = await client.login(
                        password=config.user_password,
                        device_name=config.device_name,
                    )

                    # Check if login failed
                    if type(login_response) == LoginError:
                        logger.error("Failed to login: %s", login_response.message)
                        return False
                except LocalProtocolError as e:
                    # There's an edge case here where the user hasn't installed the correct C
                    # dependencies. In that case, a LocalProtocolError is raised on login.
                    logger.fatal(
                        "Failed to login. Have you installed the correct dependencies? "
                        "https://github.com/poljar/matrix-nio#installation "
                        "Error: %s",
                        e,
                    )
                    return False

                # Login succeeded!

            logger.info(f"Logged in as {config.user_id}")
            await client.sync_forever(timeout=30000, full_state=True)

        except (ClientConnectionError, ServerDisconnectedError):
            logger.warning("Unable to connect to homeserver, retrying in 15s...")

            # Sleep so we don't bombard the server with login requests
            sleep(15)
        finally:
            # Make sure to close the client connection on disconnect
            await client.close()


# Run the main function in an asyncio event loop
asyncio.get_event_loop().run_until_complete(main())
