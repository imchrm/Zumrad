from typing import Optional
from zumrad_iis import config


class ActivationService:
    def __init__(self, keyword:str) -> None:
        self._keyword:str = keyword.lower() # Храним ключевое слово в нижнем регистре
        self._is_active:bool = False

    def is_active(self) -> bool:
        return self._is_active

    def activate(self) -> None:
        self._is_active = True

    def deactivate(self) -> None:
        self._is_active = False

    def check_and_trigger_activation(self, text:str) -> Optional[str]:
        """
        Проверяет, содержит ли текст ключевое слово активации.
        Если да, активирует сервис и возвращает текст после ключевого слова.
        Возвращает None, если ключевое слово не найдено или после него нет текста.
        """
        processed_text = text.lower()
        if processed_text.startswith(self._keyword):
            self.activate()
            command_part = processed_text[len(self._keyword):].strip()
            return command_part if command_part else None # Возвращаем часть команды или None, если только ключевое слово
        return None