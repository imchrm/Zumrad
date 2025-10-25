from datetime import datetime
import logging
from zumrad_iis.commands.command_processor import Command, IRunnerProtocol
from colorama import Fore, Back, Style


log: logging.Logger = logging.getLogger(__name__) 



class WhatTimeIsItCommand(Command):

    def __init__(self) -> None:
        ...

    async def run(self, command_name: str | None) -> None:
        current_time = datetime.now().strftime("%H:%M:%S")
        print(Fore.YELLOW + Back.GREEN + Style.DIM + f"    Time is: {current_time}                    ")
