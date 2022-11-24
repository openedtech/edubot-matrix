#!/usr/bin/env python3
import asyncio

try:
    from edubot_matrix import main

    # Run the main function of the edubot
    asyncio.get_event_loop().run_until_complete(main.main())
except ImportError as e:
    print("Unable to import edubot_matrix.main:", e)
