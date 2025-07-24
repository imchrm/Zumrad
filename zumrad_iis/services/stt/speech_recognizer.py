# speech_recognizer.py
from typing import Optional, Callable, Coroutine, Any
import asyncio
import logging
import concurrent.futures
from zumrad_iis.services.audio_input_service import AudioInputService
from zumrad_iis.services.avosk_stt import Messages, STTServiceProtocol

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
                stt: STTServiceProtocol, # Interface for realization of VoskSTTService
                recognized_text_handler: Callable[[str], Coroutine[Any, Any, None]],
                stop_handler: Callable[[], Coroutine[Any, Any, None]]
                ):
        self.audio_in = audio_in
        self.stt = stt
        self._base_event_loop: Optional[asyncio.AbstractEventLoop] = None
        self.recognized_text_handler = recognized_text_handler
        self.stop_handler = stop_handler # Корутина для завершения работы систем
        self.is_running = False
        self._is_pause = False
        self._recognition_exeption: Optional[Exception] = None
        
        self._recognition_task: Optional[asyncio.Task] = None
        
    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Устанавливает цикл событий asyncio для потокобезопасных операций."""
        self._base_event_loop = loop
        
    async def initialize(self):
        log.info("SpeechRecognizer: Инициализация сервиса распознавания речи...")
        await self.stt.initialize()
            
    def _threaded_recognition_loop(self) -> None:
        """
        Этот цикл выполняется в одном, выделенном потоке, чтобы обеспечить
        сохранность состояния для stateful STT-библиотек (Vosk).
        Он синхронно получает аудио, распознает его и передает результат
        в основной цикл событий asyncio для асинхронной обработки.
        """
        log.info("SpeechRecognizer: Потоковый цикл распознавания речи запущен.")
        if not self._base_event_loop:
            log.error("SpeechRecognizer: Цикл событий не установлен. Цикл распознавания не может быть запущен.")
            raise RuntimeError("Event loop is not set for SpeechRecognizer.")
        
        try:
            while self.is_running:
                # 1. Получаем данные из asyncio-очереди, блокируя текущий поток (не event loop)
                # до тех пор, пока корутина не завершится в основном цикле.
                if not self._is_pause:
                    future = asyncio.run_coroutine_threadsafe(self.audio_in.get_data(), self._base_event_loop)
                    audio_data = future.result()  # Блокирующий вызов

                    if audio_data is None:
                        log.info("SpeechRecognizer: Поток аудио ввода завершился в цикле распознавания.")
                        break
                    if not self.is_running:  # Проверка после блокирующего вызова
                        break

                    # 2. CPU-bound операция выполняется в том же потоке, что и предыдущая итерация.
                    # Это решает проблему сброса состояния в Vosk.
                    recognized_text = self.stt.transcribe(audio_data)

                    if not recognized_text:
                        continue

                    log.debug(f"Thread Recon >>: {recognized_text}")
                    # 3. Передаем результат обратно в основной event loop для безопасного выполнения
                    # асинхронного обработчика.
                    asyncio.run_coroutine_threadsafe(
                        self.recognized_text_handler(recognized_text),
                        self._base_event_loop
                    )
        except concurrent.futures.CancelledError:
            # Обработка отмены future.result() в Windows
            log.info("SpeechRecognizer: Потоковый цикл распознавания прерван (concurrent.futures.CancelledError).")
            # is_running уже должен быть False, но на всякий случай:
            self.is_running = False
        except asyncio.CancelledError:
            log.info("SpeechRecognizer: Потоковый цикл распознавания отменен (CancelledError).")
        except Exception as e:
            if self._is_critical_error(e):
                # Это может произойти в Windows при отмене. Не считаем это ошибкой.
                log.critical("Критическая ошибка в потоковом цикле распознавания: {e}", exc_info=True)
                if self._base_event_loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.stop(), self._base_event_loop)
            else:
                log.error(f"SpeechRecognizer: Временная ошибка в потоковом цикле распознавания: {e}")
                # Здесь можно добавить логику обработки временных ошибок, например:
                # 1. Попробовать перезапустить цикл распознавания после небольшой задержки.
                # 2. Увеличить задержку после нескольких неудачных попыток.
                # 3. Ограничить количество попыток перезапуска, чтобы избежать бесконечного цикла.
                # Например:
                # asyncio.sleep(1)
                # if self.is_running: # Проверяем, не остановлен ли сервис извне
                #     asyncio.run_coroutine_threadsafe(self.start(), self._base_event_loop)
        finally:
            # Безопасно передаем управление в основной поток для остановки
            log.debug("SpeechRecognizer: Блок finally. Гарантированный вызов stop().")
            # if self._base_event_loop.is_running():
                # asyncio.run_coroutine_threadsafe(self.stop(), self._base_event_loop)
                
    def _is_critical_error(self, e: Exception) -> bool:
        """Определяет, является ли ошибка критической."""
        # Пример: Считаем ошибкой загрузки модели критической.
        # TODO: нужно адаптировать это под конкретные ошибки и библиотеку Vosk.
        if isinstance(e, RuntimeError) and Messages.FAILED_TO_LOAD_STT_MODEL in str(e):
            return True
        # Другие ошибки, которые не считаете критическими, например, связанные с аудиоустройством.
        # elif isinstance(e, SomeOtherException) and "Specific error message" in str(e):
        #    return True
        else:
            return False
        
    async def start(self):
        """
        Запускает процесс распознавания речи.
        Создает выделенный поток для цикла распознавания, чтобы обеспечить
        целостность состояния STT-сервиса.
        """
        log.info("SpeechRecognizer: Запуск распознавания речи...")
        self.audio_in.check_capture_device()
        self.audio_in.start_capture()
        self.is_running = True
        
        # Запускаем цикл в отдельном потоке.
        # asyncio.to_thread гарантирует, что вся функция _threaded_recognition_loop
        # будет выполнена в одном потоке из пула.
        self._recognition_task = asyncio.create_task(
            asyncio.to_thread(self._threaded_recognition_loop)
        )
        
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
        self._is_pause = True
        self.audio_in.stop_capture()
        pass
    
    def resume(self):
        self._is_pause = False
        self.audio_in.start_capture()
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
            ## необязательный безопасный вызов, так как вызывается он в любом случае из базового loop
            # asyncio.run_coroutine_threadsafe(self.stop_handler(), self._base_event_loop)
            await self.stop_handler() # прямой вызов в том же event_loop
        

    
    