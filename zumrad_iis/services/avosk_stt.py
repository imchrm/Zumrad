import asyncio
from email.mime import audio
from typing import Callable, Dict, Any, List, Optional, Protocol
import logging
from vosk import Model, KaldiRecognizer
import json

from zumrad_iis.services.audio_input_service import AudioInputService

log = logging.getLogger(__name__) 

class DefaultSTTConfig:
    # STT_MODEL_NAME = "uz-UZ"  # Локаль для распознавания речи
    STT_MODEL_NAME = "ru-RU"  # Имя папки модели для распознавания речи
    STT_MODEL_PATH = "stt_models/"  # Путь к папке с распакованной моделью
    DEVICE_ID = None      # ID устройства ввода (микрофона), None - устройство по умолчанию
    SAMPLERATE = 16000    # Частота дискретизации, с которой обучена модель Vosk
    CHANNELS = 1          # Моно
    BLOCKSIZE = 8000      # Размер блока данных (в семплах) для обработки
    
    def __init__(self, model_path: str = "model", sample_rate: int = 16000):
        self.model_path = model_path
        self.sample_rate = sample_rate

# Interface
class STTProtocol(Protocol):  
    async def initialize(self) -> None:
        """
        Инициализация сервиса распознавания речи.
        Может включать загрузку модели, настройку параметров и т.д.
        """
        ...
    def transcribe(self, audio_data: bytes) -> str:
        ...

class VoskSTTService(STTProtocol):
    def __init__(self,
                model_path: str,
                audio_input: AudioInputService,
                sample_rate: int,
                ):

        self.model_path = model_path
        self.sample_rate = sample_rate
        self.audio_input = audio_input
        self.model: Optional[Model] = None
        self.recognizer: Optional[KaldiRecognizer] = None

    def transcribe(self, audio_data: bytes) -> str:
        """
        Processes an audio chunk. If the chunk completes an utterance,
        returns the recognized text. Otherwise, returns an empty string.
        """
        if not self.recognizer:
            log.warning("VoskSTTService: Распознаватель не инициализирован. Сначала вызовите initialize().")
            return ""

        if self.recognizer.AcceptWaveform(audio_data):
            result_json = self.recognizer.Result()
            try:
                result_dict = json.loads(result_json)
                return result_dict.get("text", "")
            except json.JSONDecodeError:
                log.error(f"VoskSTTService: Failed to decode JSON from Vosk: {result_json}")
                return ""
        return "" # No complete utterance recognized from this chunk yet

    async def initialize(self) -> None:
        log.info("VoskSTTService: Инициализация сервиса распознавания речи...")
        log.debug(f"VoskSTTService: Загрузка модели из {self.model_path}...")

        # Выполняем блокирующую загрузку в отдельном потоке, чтобы не блокировать event loop
        loop = asyncio.get_running_loop()
        self.model = await loop.run_in_executor(None, Model, self.model_path)

        if not self.model:
            raise RuntimeError(f"Не удалось загрузить модель Vosk из {self.model_path}.")

        self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
        self.recognizer.SetWords(True)
        log.info("VoskSTTService: Сервис распознавания речи успешно инициализирован.")