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
                error_handler: Callable[[Exception], Coroutine[Any, Any, None]],
                destroy_handler: Callable[[], Coroutine[Any, Any, None]]
                ):
        self.audio_in = audio_in
        self.stt = stt
        self._base_event_loop = base_event_loop
        self.recognized_text_handler = recognized_text_handler
        self.destroy_handler = destroy_handler # Корутина для завершения работы систем
        self.error_handler = error_handler # Корутина для обработки ошибок в основном цикле
        self.is_running = False
        
        self._recognition_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        log.info("SpeechRecognizer: Инициализация сервиса распознавания речи...")
        await self.stt.initialize()
            
    def _blocking_speech_recognition_loop(
        self,
        loop: asyncio.AbstractEventLoop,
        recognized_text_handler_coro: Callable[[str], Coroutine[Any, Any, None]],
        error_handler_coro: Callable[[Exception], Coroutine[Any, Any, None]]
    ) -> None:
        """
        Выполняется в отдельном потоке. Получает аудио, распознает и передает результат
        через callback-корутину `self.recognized_text_handler` в основной цикл событий asyncio.
        """
        log.info("VoiceAssistant: Цикл распознавания речи запущен в отдельном потоке.")
        try:
            while self.is_running: # Проверяем флаг экземпляра
                audio_data = self.audio_in.get_data() # Блокирующий вызов
                if audio_data is None: # Сигнал для остановки
                    log.info("VoiceAssistant: Поток аудио ввода завершился в цикле распознавания.")
                    break
                if not self.is_running: # Проверка после блокирующего вызова
                    break

                recognized_text = self.stt.transcribe(audio_data)

                if not recognized_text:
                    continue

                log.debug(f"Thread Recon >>: {recognized_text}")
                # Передаем управление корутине в основном цикле событий
                asyncio.run_coroutine_threadsafe(recognized_text_handler_coro(recognized_text), loop)

        except Exception as e:
            log.error(f"VoiceAssistant: Ошибка в цикле распознавания речи: {e}")
            if loop and not loop.is_closed():
                self.is_running = False  # Останавливаем ассистента
                asyncio.run_coroutine_threadsafe(error_handler_coro(e), loop)
        finally:
            log.info("VoiceAssistant: Цикл распознавания речи завершен.")
    
    async def _handle_recognition_loop_error(self, error: Exception):
        log.error(f"VoiceAssistant: Ошибка из цикла распознавания передана в основной поток: {error}")
        self.is_running = False # Останавливаем ассистента
        
    async def start(self):
        """
        Запускает процесс распознавания речи.
        Получает аудиоданные из AudioInputService, передает их в STT-сервис
        и отправляет распознанный текст в обработчик.
        """
        log.info("VoiceAssistant: Запуск распознавания речи...")
        # self._main_event_loop = asyncio.get_running_loop()
        # await self.initialize()
        
        # if not self.is_running: # Если инициализация не удалась и установила is_running = False
        #     log.error("VoiceAssistant: Не удалось инициализировать системы. Завершение работы.")
        #     await self.shutdown_systems()
        #     return
        
        self.audio_in.start_capture()
        log.info("Говорите. Для остановки нажмите Ctrl+C")
        self.is_running = True
        
        self._recognition_task = asyncio.create_task(
            asyncio.to_thread(
                self._blocking_speech_recognition_loop,
                self._base_event_loop,
                self.recognized_text_handler,
                self.error_handler
            )
        )
        
        await self._wait_for_recognition_text()
        
    async def _wait_for_recognition_text(self):
        try:
            if self._recognition_task:
                await self._recognition_task # Ожидаем завершения задачи распознавания
            else:
                # Эта ситуация не должна возникнуть, если инициализация прошла успешно
                log.error("VoiceAssistant: Задача распознавания не была создана. Завершение работы.")
                self.is_running = False

        except KeyboardInterrupt:
            log.info("\nVoiceAssistant: Завершение работы по Ctrl+C...")
            self.is_running = False
        except asyncio.CancelledError:
            log.info("VoiceAssistant: Основная задача 'run' или задача распознавания была отменена.")
            self.is_running = False
        except Exception as e:
            # Это перехватит исключения, возникшие в self._recognition_task (если они не были обработаны внутри)
            log.exception(f"VoiceAssistant: Произошла критическая ошибка: {e}")
            self.is_running = False
        finally:
            # ... (остальная часть finally остается такой же)
            log.info("VoiceAssistant: Начало процедуры остановки...")
            self.is_running = False # Убедимся, что флаг установлен для всех компонентов

            if self._recognition_task and not self._recognition_task.done():
                log.info("VoiceAssistant: Отмена задачи распознавания...")
                self._recognition_task.cancel()
                try:
                    await self._recognition_task
                except asyncio.CancelledError:
                    log.info("VoiceAssistant: Задача распознавания успешно отменена.")
                except Exception as e_cancel: # Переименовал переменную, чтобы не конфликтовала с внешней 'e'
                    log.error(f"VoiceAssistant: Ошибка при ожидании отмены задачи распознавания: {e_cancel}")

            self.audio_in.stop_capture()
            asyncio.run_coroutine_threadsafe(self.destroy_handler(), self._base_event_loop)
            await self.destroy()
            log.info("VoiceAssistant: Приложение завершило работу.")
    
    def pause(self):
        pass
    
    def resume(self):
        pass
    
    async def destroy(self):
        # Destroy elements of this class
        pass
        

    
    