# zumrad_app/core/tts_interface.py
from typing import Protocol, Any, Optional, Dict
import asyncio # Если твой TTS асинхронный

class ITextToSpeech(Protocol):
    """
    Интерфейс для движка синтеза речи (TTS).
    """

    async def load_and_init_model(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Инициализирует движок TTS.
        Может загружать модели, устанавливать соединения и т.д.
        :param config: Словарь с конфигурацией для этого TTS движка.
        :return: True, если инициализация прошла успешно, иначе False.
        """
        ... # В протоколах тело метода обозначается '...'

    async def speak(self, text: str, voice: Optional[str] = None) -> bool:
        """
        Синтезирует и воспроизводит речь.
        :param text: Текст для озвучивания.
        :param voice: (Опционально) Идентификатор голоса, если поддерживается.
        :param kwargs: Дополнительные параметры для конкретного движка.
        :return: True, если успешно, иначе False.
        """
        ...

    async def is_ready(self) -> bool:
        """
        Проверяет, готов ли движок к работе (например, модель загружена).
        :return: True, если готов, иначе False.
        """
        ...

    async def destroy(self) -> None:
        """
        Корректно завершает работу движка, освобождает ресурсы.
        """
        ...