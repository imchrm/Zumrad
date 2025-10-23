from datetime import datetime
import logging
from zumrad_iis.commands.command_processor import Command, RunnerProtocol

log: logging.Logger = logging.getLogger(__name__) 


class WhatTimeIsItCommand(Command):

    def __init__(self) -> None:
        ...

    async def run(self, command_name: str) -> None:
        await super().run(command_name)
        current_time = datetime.now().strftime("%H:%M:%S")
        log.info(f"    Time is: {current_time}")
