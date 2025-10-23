import logging
from typing import Dict, Protocol, runtime_checkable

from zumrad_iis.commands.command_vocabulary import CommandVocabulary

log: logging.Logger = logging.getLogger(__name__) 

@runtime_checkable
class RunnerProtocol(Protocol):
    """
    An Interface for command runners, ensuring they have a run method.
    """
    async def run(self, command_name: str) -> None:
        ...

class Command(RunnerProtocol):
    """
    A abstract class representing a command.
    """
    def __init__(self) -> None:
        ...
    async def run(self, command_name: str) -> None:
        log.debug(f"Executing command: {command_name}")
        ...



class CommandRunner:
    """
    A runner class for commands.
    
    Attributes:
        commands (list[str]): A list of command names.

    """
    
    def __init__(self) -> None:
        self._register: Dict[str, RunnerProtocol] = {}

        pass

    def register_command(self, command_name: str, runner: RunnerProtocol) -> None:
        """
        Register a command with its runner.
        
        Args:
            command_name (str): The name of the command.
            runner (RunnerProtocol): The runner for the command.
        """
        if runner is None:
            raise ValueError("Runner cannot be None")
        if command_name in self._register:
            raise ValueError(f"Command '{command_name}' is already registered")
        if isinstance(runner, RunnerProtocol):
            self._register[command_name] = runner
        else:
            raise ValueError(f"Invalid runner type for command '{command_name}'")

class CommandExecutor(CommandRunner):
    """
    A class that executes commands.
    """
    def __init__(self) -> None:
        super().__init__()

    async def exe(self, command_name: str) -> None:
        """
        Execute a command by its name.
        
        Args:
            command_name (str): The name of the command to execute.
        """
        runner: RunnerProtocol | None = self._register.get(command_name)
        if runner:
            log.info(f"Executing command: {command_name}")
            await runner.run(command_name)
        else:
            log.warning(f"Command '{command_name}' not found.")
        
class CommandTranslator:
    """
    A class that translates phrases to commands.
    """
    def __init__(self, vocabulary: CommandVocabulary) -> None:
        self.vocabulary: CommandVocabulary = vocabulary

        ...
    def translate(self, phrase: str) -> str | None:
        """
        Translate a phrase to a command.
        
        Args:
            phrase (str): The phrase to translate.
        
        Returns:
            str: The translated command.
        """
        return self.vocabulary.phrase_map.get(phrase, None)
        
