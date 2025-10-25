import logging
from typing import Any, Callable

from zumrad_iis.commands.command_processor import Command, IRunnerProtocol

CommandHandler = Callable[[bool], Any] # или Callable[[], None] если они ничего не возвращают

log: logging.Logger = logging.getLogger(__name__) 


class RepeatPhrasesCommand(Command):
    def __init__(self, command_handler: CommandHandler, is_repeat: bool = False) -> None:
        self.command_handler = command_handler
        self.is_repeat: bool = is_repeat
        ...

    async def run(self, command_name: str | None) -> None:
        if self.command_handler:
            self.command_handler(self.is_repeat)