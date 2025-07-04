import logging
from typing import Optional
import asyncio
import sounddevice as sd

from zumrad_iis import config

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
        self._stream = None

    def _consume_audio_data_callback(self, indata, frames, time, status):
        if status:
            log.debug(status)
        # put_nowait безопасен для вызова из другого потока (в котором работает callback)
        self.audio_queue.put_nowait(bytes(indata))

    def _check_capture_device(self):
        devices = sd.query_devices()
        name:str = ""
        log.info(f"Доступные устройства для захвата голоса:")
        if devices:
            for i, device in enumerate(devices):
                name = device.get("name", "") if isinstance(device, dict) else str(device)
                log.info(f"{i}: {name}")
        if config.STT_DEVICE_ID is not None and config.STT_DEVICE_ID >= len(devices):
            log.info(f"Устройство с ID {config.STT_DEVICE_ID} не найдено.")
            exit(1)
        current_device = sd.query_devices(config.STT_DEVICE_ID, 'input')
        if current_device:
            name = current_device.get("name", "") if isinstance(current_device, dict) else str(current_device)
            log.info(f"Используется устройство: {name if config.STT_DEVICE_ID else 'Устройство по умолчанию'}")
            
        log.debug(f"Используемые параметры захвата: "
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