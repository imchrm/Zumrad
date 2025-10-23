# main_application.py
from typing import Any, Optional, Callable, Coroutine
import asyncio
import logging
from zumrad_iis import config # Используем относительный импорт, если main.py часть пакета zumrad_iis
from zumrad_iis.services.audio_input_service import AudioInputService
from zumrad_iis.services.avosk_stt import STTService # Импортируем конфигурацию
from zumrad_iis.core.tts_interface import TextToSpeechInterface
from zumrad_iis.tts_implementations.async_silero_tts import AsyncSileroTTS
# Заглушки для будущих сервисов, чтобы код компилировался
from zumrad_iis.services.activation_service import ActivationService # Предполагаем, что такой сервис будет
from zumrad_iis.services.command_service import CommandService
from zumrad_iis.services.external_process_service import ExternalProcessService # Предполагаем, что такой сервис будет
# from services import AudioInputService, SpeechRecognitionService, ...
import zumrad_iis.commands.handlers.process_commands as process_commands # Импортируем обработчики команд
import zumrad_iis.commands.handlers.system_commands as system_commands # Импортируем системные команды

log = logging.getLogger(__name__) 

class VoiceAssistant:
    
    _IS_WAIT_FOR_RECOGNITION_TASK: bool = True  # Флаг для управления способом распознавания
    
    def __init__(self):
        # Загрузка конфигурации
        self.config = config
        # Инициализация сервисов
        self.audio_in = AudioInputService(
            config.STT_SAMPLERATE,
            config.STT_BLOCKSIZE,
            config.STT_DEVICE_ID,
            config.STT_CHANNELS
                                        )
        self.stt = STTService(model_path = config.STT_MODEL_PATH,
                                audio_input = self.audio_in,
                                sample_rate = config.STT_SAMPLERATE
                            )

        self.tts_service: TextToSpeechInterface = AsyncSileroTTS(
            language=config.TTS_LANGUAGE, # Используем config
            model_id=config.TTS_MODEL_ID, # Используем config
            sample_rate=config.TTS_SAMPLERATE, # Используем config
            # device=torch.device(config.TTS_DEVICE) # Если нужно передавать torch.device
        )

        self.activation_service = ActivationService(config.STT_KEYWORD)
        self.command_service = CommandService()
        # self.feedback = AudioFeedbackService()
        self.external_processes_service = ExternalProcessService()
        self._setup_commands() # Зарегистрируем команды

        # Состояние ассистента
        self.is_running = True  # Флаг для управления основным циклом
        self._main_event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._recognition_task: Optional[asyncio.Task] = None

    # Вспомогательные методы, перенесенные и адаптированные из a_main.py
    def _check_is_exit_phrase(self, text: str) -> bool:
        for phrase in config.PHRASES_TO_EXIT:
            if phrase in text.lower():
                return True
        return False

    async def _play_feedback_sound(self, sound_path: str):
        # Здесь в будущем будет AudioFeedbackService
        # Пока что можно использовать playsound напрямую, но это блокирующая операция
        # Для асинхронного контекста лучше использовать asyncio.to_thread
        # или специализированный асинхронный сервис воспроизведения.
        # Для примера, пока оставим простой вызов, но это место для улучшения.
        log.debug(f"Playing sound: {sound_path}")
        # playsound(sound_path) # Это блокирует!
        # Вместо этого, если playsound используется:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: __import__('playsound').playsound(sound_path))
        except Exception as e:
            log.error(f"Failed to play sound {sound_path}: {e}")

    def _setup_commands(self):
        self.command_service.register_command("запусти видеоплеер", process_commands.launch_video_player)
        self.command_service.register_command("сколько времени", system_commands.what_time_is_it)
        # ... и так далее
        pass
    
    async def initialize_systems(self):
        # ... инициализация других систем ...
        await self.stt.initialize() # Инициализация STT

        log.info("VoiceAssistant: Инициализация сервиса синтеза речи...")
        if self.tts_service and hasattr(self.tts_service, 'load_and_init_model'):
            if not await self.tts_service.load_and_init_model():
                log.error("Не удалось инициализировать сервис синтеза речи!")
                # self.is_running = False # Раскомментируйте, если TTS критичен для работы
            else:
                log.info("Сервис синтеза речи успешно инициализирован.")
        else:
            log.warning("TTS service does not have 'load_and_init_model' or is None.")


    async def say(self, text: str, voice: Optional[str] = None):
        if await self.tts_service.is_ready():
            # Голос по умолчанию можно брать из конфигурации, если не передан
            speaker_voice = voice or config.TTS_VOICE # Используем актуальный голос из config
            await self.tts_service.speak(text, voice=speaker_voice)
        else:
            log.warning("Сервис TTS не готов, не могу произнести текст.")
            log.debug(f"ASSISTANT (fallback): {text}") # Запасной вариант вывода

    def _blocking_speech_recognition_loop(
        self,
        loop: asyncio.AbstractEventLoop,
        recognized_text_handler_coro: Callable[[str], Coroutine[Any, Any, None]]
    ) -> None:
        """
        Выполняется в отдельном потоке. Получает аудио, распознает и передает результат
        через callback-корутину в основной цикл событий asyncio.
        """
        log.info("VoiceAssistant: Цикл распознавания речи запущен в отдельном потоке.")
        try:
            while self.is_running:
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
                asyncio.run_coroutine_threadsafe(self._handle_recognition_loop_error(e), loop)
        finally:
            log.info("VoiceAssistant: Цикл распознавания речи завершен.")

    async def _handle_recognition_loop_error(self, error: Exception):
        log.error(f"VoiceAssistant: Ошибка из цикла распознавания передана в основной поток: {error}")
        self.is_running = False # Останавливаем ассистента

    async def _process_recognized_text(self, recognized_text: str):
        """
        Эта корутина выполняется в основном цикле asyncio и обрабатывает распознанный текст.
        """
        log.info(f"MainLoop CB <<: {recognized_text}")

        if self._check_is_exit_phrase(recognized_text):
            log.info("VoiceAssistant: Завершение работы по команде выхода...")
            await self.say("Завершаю работу.", voice=self.config.TTS_VOICE)
            self.is_running = False # Сигнал для остановки всех циклов
            return

        if self.activation_service.is_active():
            # Если self.command_service.execute_command может быть долгим,
            # его также стоит запускать через await asyncio.to_thread(...)
            command_executed = self.command_service.execute_command(recognized_text)
            if command_executed:
                log.info(f"VoiceAssistant: Команда '{recognized_text}' выполнена.")
                await self._play_feedback_sound(self.config.COMMAND_SOUND_PATH)
                self.activation_service.deactivate()
                self.audio_in.clear_queue()
            else:
                log.warning(f"VoiceAssistant: Команда не распознана: {recognized_text}")
                # await self.say("Команда не распознана.", voice=self.config.TTS_VOICE)
        else: # Система не активирована
            processed_text_after_keyword = self.activation_service.check_and_trigger_activation(recognized_text)

            if self.activation_service.is_active(): # Если только что активировалась
                await self._play_feedback_sound(self.config.ACTIVATION_SOUND_PATH)
                self.audio_in.clear_queue()

                if processed_text_after_keyword:
                    log.info(f"VoiceAssistant: Команда после активации: {processed_text_after_keyword}")
                    command_executed = self.command_service.execute_command(processed_text_after_keyword)
                    if command_executed:
                        await self._play_feedback_sound(self.config.COMMAND_SOUND_PATH)
                        self.activation_service.deactivate()
                        self.audio_in.clear_queue()
                    else:
                        log.warning(f"VoiceAssistant: Команда после активации не распознана: {processed_text_after_keyword}")
                        # await self.say("Команда не ясна.", voice=self.config.TTS_VOICE)
                        # Остаемся активными, ждем следующую команду
                else:
                    log.info(f"VoiceAssistant: Ключевое слово '{self.config.STT_KEYWORD}' распознано! Жду вашу команду...")
                    # await self.say("Слушаю.", voice=self.config.TTS_VOICE)

    async def run(self):
        log.info("VoiceAssistant: Запуск основного приложения...")
        self._main_event_loop = asyncio.get_running_loop()
        await self.initialize_systems()

        # if not self.is_running: # Если инициализация не удалась и установила is_running = False
        #     log.error("VoiceAssistant: Не удалось инициализировать системы. Завершение работы.")
        #     await self.shutdown_systems()
        #     return

        self.audio_in.start_capture()
        log.info("Говорите. Для остановки нажмите Ctrl+C")
        self.is_running = True # Устанавливаем флаг, что ассистент запущен
        # Запускаем блокирующий цикл распознавания в отдельном потоке
        self._recognition_task = self._main_event_loop.create_task(
            asyncio.to_thread(
                self._blocking_speech_recognition_loop,
                self._main_event_loop,
                self._process_recognized_text # Передаем ссылку на корутину-обработчик распознанного текста
            )
        )
        if VoiceAssistant._IS_WAIT_FOR_RECOGNITION_TASK:
            await self._wait_for_recognition_task()
        else:
            # Если нужно ждать завершения задачи распознавания в основном цикле
            await self._wait_for_recognition_while()
        
    async def _wait_for_recognition_while(self):
        try:
            while self.is_running:
                await asyncio.sleep(0.1) # Основной цикл ждет, обработка в callback
                if self._recognition_task and self._recognition_task.done():
                    try:
                        self._recognition_task.result() # Поднимет исключение, если оно было в задаче
                    except asyncio.CancelledError:
                        log.info("VoiceAssistant: Задача распознавания была отменена.")
                    except Exception as e:
                        log.error(f"VoiceAssistant: Задача распознавания завершилась с ошибкой: {e}")
                        self.is_running = False # Останавливаем, если задача распознавания упала
                    break # Выходим из основного цикла, если задача распознавания завершена

        except KeyboardInterrupt:
            log.info("\nVoiceAssistant: Завершение работы по Ctrl+C...")
            self.is_running = False
        except Exception as e: # Более общая обработка ошибок
            log.exception(f"VoiceAssistant: Произошла критическая ошибка в основном цикле: {e}")
            self.is_running = False
        finally:
            log.info("VoiceAssistant: Начало процедуры остановки...")
            self.is_running = False # Убедимся, что флаг установлен для всех компонентов

            if self._recognition_task and not self._recognition_task.done():
                log.info("VoiceAssistant: Отмена задачи распознавания...")
                self._recognition_task.cancel()
                try:
                    await self._recognition_task
                except asyncio.CancelledError:
                    log.info("VoiceAssistant: Задача распознавания успешно отменена.")
                except Exception as e:
                    log.error(f"VoiceAssistant: Ошибка при ожидании отмены задачи распознавания: {e}")

            self.audio_in.stop_capture()
            await self.shutdown_systems()
            log.info("VoiceAssistant: Приложение завершило работу.")

    async def _wait_for_recognition_task(self):
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
            await self.shutdown_systems()
            log.info("VoiceAssistant: Приложение завершило работу.")
    
    async def shutdown_systems(self):
        # ... остановка других сервисов ...
        if self.tts_service and hasattr(self.tts_service, 'is_ready') and await self.tts_service.is_ready():
            await self.tts_service.destroy()
            log.info("Сервис синтеза речи остановлен.")
        else:
            log.info("Сервис синтеза речи не был инициализирован или уже остановлен.")

async def main():
    # Настройка логирования должна быть здесь, если run.py не используется как точка входа
    # или если вы хотите переопределить настройки из run.py
    logging.basicConfig(
        level=logging.INFO, # или config.LOG_LEVEL
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    assistant = VoiceAssistant()
    await assistant.run()
    exit(1)  # Завершаем программу с кодом 0 (успешно)

if __name__ == '__main__':
    asyncio.run(main())