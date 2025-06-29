from operator import is_
from typing import Callable, Dict, Any, List, Optional
import logging

log = logging.getLogger(__name__) 

# Определяем тип для наших функций-обработчиков.
# Они не принимают аргументов (пока) и могут возвращать что угодно (или ничего - None).
CommandHandler = Callable[[], Any] # или Callable[[], None] если они ничего не возвращают


class CommandService:
    def __init__(self) -> None:
        self._command_map: Dict[str, CommandHandler] = dict[str, CommandHandler]()
    
    def execute_command(self, command_name: str) -> bool:
        is_executed: bool = False
        if command_name in self._command_map:
            self._command_map[command_name]()
            is_executed = True
        else:
            log.warning(f"Команда '{command_name}' не найдена.")
        return is_executed
    
    def register_command(self, command_name: str, handler: CommandHandler) -> None:
        """
        Регистрирует новую команду в сервисе.
        """
        if command_name in self._command_map:
            log.warning(f"Команда '{command_name}' уже зарегистрирована. Перезапись.")
        self._command_map[command_name] = handler
        log.info(f"Команда '{command_name}' успешно зарегистрирована.")