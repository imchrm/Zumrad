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
            
    def _blocking_speech_recognition_loop(
        self,
        loop: asyncio.AbstractEventLoop,
        recognized_text_handler_coro: Callable[[str], Coroutine[Any, Any, None]],
        # error_handler_coro: Callable[[Exception], Coroutine[Any, Any, None]]
    ) -> None:
        """
        Выполняется в отдельном потоке. Получает аудио, распознает и передает результат
        через callback-корутину `self.recognized_text_handler` в основной цикл событий asyncio.
        """
        log.debug("SpeechRecognizer: Цикл распознавания речи запущен в отдельном потоке.")
        log.info("Говорите. Для остановки нажмите Ctrl+C")
        # try: вынес перехват всех экзепшинов в вызываемый метод
        while self.is_running: # Проверяем флаг экземпляра
            audio_data = self.audio_in.get_data() # Блокирующий вызов
            if audio_data is None: # Сигнал для остановки
                log.info("SpeechRecognizer: Поток аудио ввода завершился в цикле распознавания.")
                break
            if not self.is_running: # Проверка после блокирующего вызова
                break

            recognized_text = self.stt.transcribe(audio_data)

            if not recognized_text:
                continue

            log.debug(f"Thread Recon >>: {recognized_text}")
                # Передаем управление корутине в основном цикле событий
            asyncio.run_coroutine_threadsafe(recognized_text_handler_coro(recognized_text), loop)
                # После передачи управления и выполнения цикл сразу возобновится 
                # TODO: проверить не будет ли это местом потенциальной проблемы?
                # await asyncio.sleep(0.01)

        # except Exception as e:
        #     log.error(f"SpeechRecognizer: Ошибка в цикле распознавания речи: {e}")
        #     # TODO нужно ли в случае Exception прекращать обработку речи 
        #     # и это именно Eception или Error о котором достаточно уведомить 
        #     # и можно продолжить обработку речи?
        #     if loop and not loop.is_closed():
        #         self.is_running = False  # Останавливаем ассистента
        #         self._recognition_exeption = e # сохраняем Exception, чтобы не плодить 
                
        # finally:
        #     log.info("SpeechRecognizer: Цикл распознавания речи завершен.")
        #     # Здесь надо запустить завершение и остановку
            
        #     if loop and not loop.is_closed():
        #         asyncio.run_coroutine_threadsafe(self.stop(self._recognition_exeption), loop)
        #         # if self._recognition_exeption:
        #         #     asyncio.run_coroutine_threadsafe(error_handler_coro(self._recognition_exeption), loop)
    
    async def _handle_recognition_loop_error(self, error: Exception):
        log.error(f"SpeechRecognizer: Ошибка из цикла распознавания возвращается в основной поток: {error}")
        self.is_running = False # Останавливаем ассистента
        
    async def start(self):
        """
        Запускает процесс распознавания речи.
        Получает аудиоданные из AudioInputService, передает их в STT-сервис
        и отправляет распознанный текст в обработчик.
        """
        log.info("SpeechRecognizer: Запуск распознавания речи...")
        # self._main_event_loop = asyncio.get_running_loop()
        # await self.initialize()
        
        # if not self.is_running: # Если инициализация не удалась и установила is_running = False
        #     log.error("SpeechRecognizer: Не удалось инициализировать системы. Завершение работы.")
        #     await self.shutdown_systems()
        #     return
        
        self.audio_in.start_capture()
        # log.info("Говорите. Для остановки нажмите Ctrl+C")
        self.is_running = True
        
        self._recognition_task = asyncio.create_task(
            asyncio.to_thread(
                self._blocking_speech_recognition_loop,
                self._base_event_loop,
                self.recognized_text_handler,
                # self.error_handler
            )
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
        

    
    