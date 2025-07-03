# speech_recognizer.py
from typing import Optional, Callable, Coroutine, Any
import asyncio
import logging
from zumrad_iis import config # Используем относительный импорт, если main.py часть пакета zumrad_iis
from zumrad_iis.services.audio_input_service import AudioInputService
from zumrad_iis.services.avosk_stt import STTProtocol, VoskSTTService # Импортируем конфигурацию

log = logging.getLogger(__name__) 

class SpeechRecognizer:
    """
    Класс для управления процессом распознавания речи.
    Отвечает за получение аудиоданных, передачу их в STT-сервис
    и отправку распознанного текста в обработчик.
    Работает в отдельном потоке, чтобы не блокировать основной цикл asyncio.
    """
    def __init__(self,
                audio_in: AudioInputService,
                stt: STTProtocol, # Interface for realization of VoskSTTService
                base_event_loop: asyncio.AbstractEventLoop,
                recognized_text_handler: Callable[[str], Coroutine[Any, Any, None]],
                # is_running: Callable[[], bool],
                # error_handler: Callable[[Exception], Coroutine[Any, Any, None]],
                stop_handler: Callable[[], Coroutine[Any, Any, None]]
                ):
        self.audio_in = audio_in
        self.stt = stt
        self._base_event_loop = base_event_loop
        self.recognized_text_handler = recognized_text_handler
        self.stop_handler = stop_handler # Корутина для завершения работы систем
        # self.error_handler = error_handler # Корутина для обработки ошибок в основном цикле
        self.is_running = False
        self._recognition_exeption: Optional[Exception] = None
        
        self._recognition_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        log.info("SpeechRecognizer: Инициализация сервиса распознавания речи...")
        await self.stt.initialize()
            
    async def _async_recognition_loop(self) -> None:
        """
        Основной асинхронный цикл распознавания речи.
        Асинхронно получает аудио, передает CPU-bound задачу распознавания в executor
        и вызывает обработчик с результатом.
        """
        log.debug("SpeechRecognizer: Асинхронный цикл распознавания речи запущен.")
        log.info("Говорите. Для остановки нажмите Ctrl+C")
        while self.is_running:
            audio_data = await self.audio_in.get_data() # 1. Асинхронное получение данных
            if audio_data is None:
                log.info("SpeechRecognizer: Поток аудио ввода завершился в цикле распознавания.")
                break
            if not self.is_running: # Проверка после ожидания
                break

            # 2. CPU-bound операция выполняется в отдельном потоке, не блокируя event loop
            recognized_text = await asyncio.to_thread(self.stt.transcribe, audio_data)

            if not recognized_text:
                continue

            log.debug(f"Thread Recon >>: {recognized_text}")
            # 3. Прямой асинхронный вызов обработчика
            await self.recognized_text_handler(recognized_text)
    
    async def start(self):
        """
        Запускает процесс распознавания речи.
        Получает аудиоданные из AudioInputService, передает их в STT-сервис
        и отправляет распознанный текст в обработчик.
        """
        log.info("SpeechRecognizer: Запуск распознавания речи...")
        self.audio_in.start_capture()
        self.is_running = True
        
        # Запускаем наш новый асинхронный цикл как задачу
        self._recognition_task = asyncio.create_task(self._async_recognition_loop())
        
        try:
            if self._recognition_task:
                await self._recognition_task # Основное ожидание завершения задачи распознавания
            else:
                # Эта ситуация не должна возникнуть, если инициализация прошла успешно
                log.error("SpeechRecognizer: Задача распознавания не была создана. Завершение работы.")
                # self.is_running = False потому что флаг установится ниже в final

        except KeyboardInterrupt:
            # Это ожидаемое исключение при Ctrl+C. Логируем как info, не как ошибку.
            log.info("\nSpeechRecognizer: Получен сигнал KeyboardInterrupt (Ctrl+C). Начинается остановка...")
            # Не нужно пробрасывать исключение, finally выполнит очистку.
        except asyncio.CancelledError:
            # Это стандартный способ asyncio остановить задачу. Тоже не ошибка.
            log.info("SpeechRecognizer: Задача распознавания была отменена. Это штатное завершение.")
            # Не нужно пробрасывать исключение, так как это часть процесса остановки.
        except Exception as e:
            # А вот это уже настоящая, непредвиденная ошибка.
            log.exception(f"SpeechRecognizer: Произошла критическая ошибка в задаче распознавания: {e}")
            raise # Пробрасываем, чтобы внешний код знал о проблеме.
        finally:
            log.debug("SpeechRecognizer: Блок finally. Гарантированный вызов stop().")
            await self.stop()
    
    def pause(self):
        pass
    
    def resume(self):
        pass
    
    async def stop(self):
        if self.is_running:
            log.info("SpeechRecognizer: Начало процедуры остановки...")
            self.is_running = False

            if self._recognition_task and not self._recognition_task.done():
                log.info("SpeechRecognizer: Отмена задачи распознавания...")
                self._recognition_task.cancel()
                try:
                    await self._recognition_task
                except asyncio.CancelledError:
                    # Это ожидаемое исключение после отмены задачи.
                    log.info("SpeechRecognizer: Задача распознавания успешно отменена и завершена.")
                except Exception as e_cancel: # Переименовал переменную, чтобы не конфликтовала с внешней 'e'
                    log.error(f"SpeechRecognizer: Ошибка при ожидании отмены задачи распознавания: {e_cancel}")

            self.audio_in.stop_capture()
            # необязательный безопасный вызов, так как вызывается он в любом случае из базового loop
            # asyncio.run_coroutine_threadsafe(self.stop_handler(), self._base_event_loop)
            await self.stop_handler() # прямой вызов в том же event_loop
        

    
    