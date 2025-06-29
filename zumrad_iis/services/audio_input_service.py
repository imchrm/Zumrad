import logging
import queue
from typing import Optional
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
        self.audio_queue = queue.Queue()
        self._stream = None

    def _consume_audio_data_callback(self, indata, frames, time, status):
        if status:
            log.debug(status)
        self.audio_queue.put(bytes(indata))

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
            # Put a sentinel value to unblock any pending queue.get() calls
            self.audio_queue.put(None)
            log.info("Audio capture stopped.")
        self.clear_queue()

    def get_data(self) -> Optional[bytes]:
        """
        Извлекает аудиоданные из очереди.
        Блокируется до тех пор, пока элемент не станет доступен или не истечет таймаут.

        Args:
            timeout: Максимальное время ожидания в секундах.
            Если None, блокируется до появления элемента.
            (Note: Timeout is removed, this method now blocks indefinitely until data or sentinel)

        Returns:
            Аудиоданные в виде байтов, или None if the sentinel value is received.
        """
        # This will block until an item is available or the sentinel (None) is put
        return self.audio_queue.get()

    def clear_queue(self):
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        log.debug("Audio queue cleared.")