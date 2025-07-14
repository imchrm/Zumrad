import logging
from typing import Optional
import asyncio
import sounddevice as sd

log = logging.getLogger(__name__) 


class AudioInputService:
    DATA_FORMAT: str = "int16"  # Тип данных для аудиопотока
    """
    Сервис для захвата аудиоданных с микрофона.
    Использует библиотеку sounddevice для захвата аудио в реальном времени.
    """
    def __init__(self, samplerate, blocksize, device_id, channels):
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.device_id = device_id
        self.channels = channels
        self.audio_queue = asyncio.Queue() # Меняем на asyncio.Queue
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stream = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Устанавливает цикл событий asyncio для потокобезопасных операций."""
        self._loop = loop

    def _consume_audio_data_callback(self, indata, frames, time, status):
        if status:
            log.debug(status)
        
        if self._loop:
            # Это потокобезопасный способ добавления элементов в asyncio.Queue
            # из другого потока (например, того, который использует sounddevice).
            self._loop.call_soon_threadsafe(self.audio_queue.put_nowait, bytes(indata))
        else:
            log.warning("AudioInputService: Цикл событий не установлен. Аудиоданные могут быть потеряны.")

    def _check_capture_device(self):
        devices = sd.query_devices()
        name:str = ""
        log.info(f"Доступные устройства для захвата голоса:")
        if devices:
            for i, device in enumerate(devices):
                name = device.get("name", "") if isinstance(device, dict) else str(device)
                log.info(f"{i}: {name}")
        if self.device_id is not None and self.device_id >= len(devices):
            log.info(f"Устройство с ID {self.device_id} не найдено.")
            exit(1)
        current_device = sd.query_devices(self.device_id, 'input')
        if current_device:
            name = current_device.get("name", "") if isinstance(current_device, dict) else str(current_device)
            log.info(f"Используется устройство: {name}")
            
        log.info(f"Используемые параметры захвата: "
                f"ID устройства: {self.device_id}, "
                f"Частота дискретизации: {self.samplerate}, "
                f"Размер блока: {self.blocksize}, "
                f"Каналы: {self.channels}, ")
    
    def start_capture(self):
        self._check_capture_device()
        # Важно: sd.RawInputStream сам по себе контекстный менеджер.
        # Если мы хотим управлять им из класса, нужно либо передавать его
        # в __enter__/__exit__ самого сервиса, либо управлять им явно.
        # Для простоты, можно создать поток и закрывать его в методе stop().
        # Либо, VoiceAssistant будет использовать 'with service.capture_context():'
        # Пока оставим как есть, но это место для улучшения.
        self._stream = sd.RawInputStream(
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            device=self.device_id,
            dtype=AudioInputService.DATA_FORMAT,
            channels=self.channels,
            callback=self._consume_audio_data_callback
        )
        self._stream.start()
        log.info("Audio capture started.")

    
    
    def stop_capture(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            # Помещаем значение-сигнал для разблокировки ожидающих вызовов queue.get()
            self.audio_queue.put_nowait(None)
            log.info("Audio capture stopped.")
        self.clear_queue()

    async def get_data(self) -> Optional[bytes]:
        """
        Извлекает аудиоданные из очереди.
        Асинхронно ожидает, пока элемент не станет доступен.

        Returns:
            Аудиоданные в виде байтов, или None, если получен сигнал остановки.
        """
        # Теперь это асинхронное ожидание
        return await self.audio_queue.get()

    def clear_queue(self):
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        log.debug("Audio queue cleared.")