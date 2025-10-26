import asyncio
import logging
from typing import Dict, Protocol, runtime_checkable
from abc import ABC, abstractmethod

from zumrad_iis.commands.command_vocabulary import CommandVocabulary, Vocabulary
from zumrad_iis.services.audio_feedback_service import AudioFeedbackService

log: logging.Logger = logging.getLogger(__name__) 

@runtime_checkable
class IRunnerProtocol(Protocol):
    """
    An Interface for command runners, ensuring they have a run method.
    """
    async def run(self, command_name: str) -> None:
        ...

class Command(ABC, IRunnerProtocol):
    """
    An Abstract Class representing a command.
    """
    def __init__(self) -> None:
        ...

    @abstractmethod
    async def run(self, command_name: str | None) -> None:
        ...

class CommandRunner(ABC):
    """
    An abstract base class for command runners.
    It defines the interface for registering commands and an abstract method
    Attributes:
        commands (list[str]): A list of command names.

    """
    
    def __init__(self) -> None:
        self._register: Dict[str, IRunnerProtocol] = {}
        ...

    def register_command(self, command_name: str, runner: IRunnerProtocol) -> None:
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
        if isinstance(runner, IRunnerProtocol):
            self._register[command_name] = runner
        else:
            raise ValueError(f"Invalid runner type for command '{command_name}'")
        
    @abstractmethod # Теперь _process_registered_command является абстрактным методом
    async def _process_registered_command(self, command_name: str) -> None:
        """
        Process a registered command.
        
        Args:
            command_name (str): The name of the command to process.
        """

class CommandExecutor(CommandRunner):
    """
    A class that executes commands.
    """
    def __init__(self, audio_feedback_service: AudioFeedbackService) -> None:
        super().__init__()
        self.audio_feedback_service: AudioFeedbackService = audio_feedback_service
        ...

    async def _process_registered_command(self, command_name: str) -> None:
        """
        Execute a command by its name.
        
        Args:
            command_name (str): The name of the command to execute.
        """
        runner: IRunnerProtocol | None = self._register.get(command_name)
        if runner:
            log.info(f"Executing command: {command_name}")
            await runner.run(command_name)
        else:
            log.warning(f"Command '{command_name}' not found.")

    async def exe(self, command_name: str) -> bool:
        """
        Execute a command by its name.
        
        Args:
            command_name (str): The name of the command to execute.
        """
        is_command_was_executed: bool = False
        if command_name in self._register:
            await self._process_registered_command(command_name) # Вызываем реализованную абстрактную логику
            await self.audio_feedback_service.play_sound(self.audio_feedback_service.sound_path)
            is_command_was_executed = True
            
        return is_command_was_executed



class CommandTranslator:
    """
    A class that translates phrases to commands.
    """
    def __init__(self, vocabulary: Vocabulary) -> None:
        self.vocabulary: Vocabulary = vocabulary

        ...
    def translate(self, phrase: str) -> str | None:
        """
        Translate a phrase to a command.
        
        self.vocabulary.phrase_map: Dict[key_phrase: str, value_command: str]

        Args:
            phrase (str): The phrase to translate.
        
        Returns:
            str: The translated command.
        """
        return self.vocabulary.vocabulary_map.get(phrase, None)
        
class CommandProcessor():
    """
    A class that processes commands.
    """
    def __init__(self, executor: CommandExecutor, translator: CommandTranslator) -> None:
        self.executor: CommandExecutor = executor
        self.translator: CommandTranslator = translator
        
    def register_command(self, command_name: str, command: Command) -> None:
        self.executor.register_command(command_name, command)

    async def process(self, phrase: str) -> bool:
        """
        Process a phrase.
        
        Args:
            phrase (str): The phrase to process.
        """
        is_command_was_executed: bool = False
        command_name: str | None = self.translator.translate(phrase)
        if command_name:
            is_command_was_executed = await self.executor.exe(command_name)
        return is_command_was_executed
    
            
        
    