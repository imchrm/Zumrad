from typing import Optional
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

class PVoiceAssistant:
    """
    Основной класс для распознавания речи и управления голосовым ассистентом.
    Выделен в отдельный класс для будущего тестирования.
    Инициализирует все необходимые сервисы и запускает основной цикл.
    Использует асинхронный подход для обработки аудио и команд.
    Основные компоненты:
    - AudioInputService: для захвата аудио с микрофона.
    - VoskSTTService: для распознавания речи с использованием модели Vosk.
    - AsyncSileroTTS: для синтеза речи.
    - ActivationService: для активации голосового ассистента по ключевому слову.
    - CommandService: для обработки команд, распознанных из речи.
    - ExternalProcessService: для управления внешними процессами (например, запуск видеоплеера).
    Основной метод run() запускает асинхронный цикл, который обрабатывает аудио,
    распознает речь и выполняет команды.
    Использует asyncio для асинхронного выполнения задач и управления состоянием ассистента.
    Также реализует методы для инициализации систем, воспроизведения звуковых сигналов
    и управления состоянием ассистента.
    """
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
        self.is_running = True # Флаг для управления основным циклом

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
        self.command_service.register_command("запусти видеоплеер", process_commands.launch_videoplayer)
        self.command_service.register_command("сколько времени", system_commands.what_time_is_it)
        # ... и так далее
        pass
    
    async def initialize_systems(self):
        # ... инициализация других систем ...
        
        self.stt.initialize() # Инициализация STT
        
        log.info("VoiceAssistant: Инициализация сервиса синтеза речи...")
        # if not await self.tts_service.load_and_init_model():
        #     log.error("Не удалось инициализировать сервис синтеза речи!")
        #     # Возможно, здесь стоит предпринять какие-то действия или завершить работу
        # else:
        #     log.info("Сервис синтеза речи успешно инициализирован.")

    async def say(self, text: str, voice: Optional[str] = None):
        if await self.tts_service.is_ready():
            # Голос по умолчанию можно брать из конфигурации, если не передан
            speaker_voice = voice or config.TTS_VOICE # Используем актуальный голос из config
            await self.tts_service.speak(text, voice=speaker_voice)
        else:
            log.warning("Сервис TTS не готов, не могу произнести текст.")
            log.debug(f"ASSISTANT (fallback): {text}") # Запасной вариант вывода
        
    async def _audio_input_loop(self, audio_chunks_queue: asyncio.Queue):
        """Отдельная задача для непрерывного получения аудио."""
        log.info("VoiceAssistant: Запуск цикла получения аудио...")
        loop = asyncio.get_running_loop()
        try:
            while self.is_running:
                try:
                    # Вызываем блокирующий get_data в executor.
                    audio_data = await loop.run_in_executor(
                        None,
                        self.audio_in.get_data
                    )
                    if audio_data is None:
                        log.info("VoiceAssistant: Получен сигнал остановки из очереди аудио (в _audio_input_loop).")
                        await audio_chunks_queue.put(None) # Сигнал для обработчика
                        break
                    await audio_chunks_queue.put(audio_data)
                except Exception as e:
                    log.error(f"VoiceAssistant: Ошибка при получении аудиоданных: {e}")
                    # Можно добавить небольшую паузу, чтобы не зацикливаться на ошибке
                    await asyncio.sleep(0.1)
                    # Если ошибка критическая, возможно, стоит остановить is_running
                    # self.is_running = False
                    # await audio_chunks_queue.put(None) # Сигнал для обработчика
                    # break
        finally:
            log.info("VoiceAssistant: Цикл получения аудио завершен.")


    async def _recognition_and_command_loop(self, audio_chunks_queue: asyncio.Queue):
        """Отдельная задача для распознавания и обработки команд."""
        log.info("VoiceAssistant: Запуск цикла распознавания и команд...")
        loop = asyncio.get_running_loop()
        try:
            while self.is_running:
                audio_data = await audio_chunks_queue.get()
                if audio_data is None:
                    log.info("VoiceAssistant: Получен сигнал остановки для цикла распознавания.")
                    break

                # Блокирующая операция STT в executor
                recognized_text = await loop.run_in_executor(None, self.stt.transcribe, audio_data)

                if not recognized_text:
                    audio_chunks_queue.task_done() # Важно для asyncio.Queue
                    continue

                log.info(f">>: {recognized_text}")
                
                # Ваша логика обработки recognized_text (выход, активация, команды)
                # Эту часть тоже можно вынести в create_task, если обработка команды долгая
                # и вы хотите, чтобы распознавание следующего чанка началось немедленно.
                # Для простоты пока оставим здесь.

                if self._check_is_exit_phrase(recognized_text):
                    log.info("VoiceAssistant: Завершение работы по команде выхода...")
                    await self.say("Завершаю работу.", voice=config.TTS_VOICE)
                    self.is_running = False # Сигнал для всех циклов
                    # audio_chunks_queue.task_done() # Важно
                    # break # Выходим из этого цикла, is_running остановит и другие
                elif self.activation_service.is_active():
                    command_executed = await loop.run_in_executor(None, self.command_service.execute_command, recognized_text) # Если execute_command блокирующий
                    # Или если execute_command асинхронный:
                    # command_executed = await self.command_service.execute_command_async(recognized_text)

                    if command_executed:
                        log.info(f"VoiceAssistant: Команда '{recognized_text}' выполнена.")
                        await self._play_feedback_sound(config.COMMAND_SOUND_PATH)
                        self.activation_service.deactivate()
                        # Очистка очереди аудио_ввода может быть не нужна здесь,
                        # так как аудио уже обработано до этого момента.
                        # self.audio_in.clear_queue() # Подумать, нужна ли и где
                    else:
                        log.warning(f"VoiceAssistant: Команда не распознана: {recognized_text}")
                else: # Система не активирована
                    # Логика активации. check_and_trigger_activation должен быть быстрым.
                    # Если он делает что-то долгое, его тоже в executor.
                    # Предположим, он быстрый:
                    processed_text_after_keyword = self.activation_service.check_and_trigger_activation(recognized_text) # Должен вернуть текст команды или None/пусто
                    
                    if self.activation_service.is_active(): # Если только что активировалась
                        await self._play_feedback_sound(config.ACTIVATION_SOUND_PATH)
                        # self.audio_in.clear_queue() # Подумать

                        if processed_text_after_keyword:
                            log.info(f"VoiceAssistant: Команда после активации: {processed_text_after_keyword}")
                            # command_executed = self.command_service.execute_command(processed_text_after_keyword)
                            command_executed = await loop.run_in_executor(None, self.command_service.execute_command, processed_text_after_keyword)

                            if command_executed:
                                await self._play_feedback_sound(config.COMMAND_SOUND_PATH)
                                self.activation_service.deactivate()
                            else:
                                log.warning(f"VoiceAssistant: Команда после активации не распознана: {processed_text_after_keyword}")
                        else:
                            log.info(f"VoiceAssistant: Ключевое слово '{config.STT_KEYWORD}' распознано! Жду вашу команду...")
                
                audio_chunks_queue.task_done() # Важно для asyncio.Queue
        except Exception as e: # Ловим ошибки конкретно этого цикла
            log.exception(f"VoiceAssistant: Ошибка в цикле распознавания/команд: {e}")
            self.is_running = False # Останавливаем все в случае серьезной ошибки
        finally:
            log.info("VoiceAssistant: Цикл распознавания и команд завершен.")


    async def run(self):
        log.info("VoiceAssistant: Запуск основного приложения...")
        await self.initialize_systems()

        self.audio_in.start_capture()
        log.info("Говорите. Для остановки нажмите Ctrl+C")
        self.is_running = True

        audio_chunks_queue = asyncio.Queue(maxsize=10) # Ограничиваем размер очереди

        # Запускаем циклы как независимые задачи
        audio_input_task = asyncio.create_task(self._audio_input_loop(audio_chunks_queue))
        recognition_task = asyncio.create_task(self._recognition_and_command_loop(audio_chunks_queue))

        try:
            # Ожидаем завершения одной из задач (или обеих, если is_running станет False)
            # Можно использовать asyncio.gather или просто ждать одну, а is_running остановит другую.
            # Если audio_input_task завершится (например, из-за None от get_data),
            # он положит None в очередь, что остановит recognition_task.
            # Если recognition_task упадет, он установит self.is_running = False, что остановит audio_input_task.
            
            # Ждем, пока обе задачи не завершатся или не возникнет исключение
            done, pending = await asyncio.wait(
                [audio_input_task, recognition_task],
                return_when=asyncio.FIRST_COMPLETED # Ждем завершения первой задачи
            )

            # Если одна из задач завершилась с ошибкой, она будет здесь
            for task in done:
                if task.exception():
                    log.error(f"VoiceAssistant: Задача {task.get_name()} завершилась с ошибкой: {task.exception()}")
                    self.is_running = False # Убедимся, что все останавливается

            # Даем шанс оставшимся задачам завершиться, если is_running стал False
            if pending:
                await asyncio.wait(pending) # Ждем оставшиеся

        except KeyboardInterrupt:
            log.info("\nVoiceAssistant: Завершение работы по Ctrl+C...")
            self.is_running = False
        except Exception as e:
            log.exception(f"VoiceAssistant: Произошла критическая ошибка в run(): {e}")
            self.is_running = False
        finally:
            log.info("VoiceAssistant: Начало процедуры остановки...")
            self.is_running = False # Убедимся, что флаг установлен для всех циклов

            # Явно отменяем задачи, если они еще работают, и ждем их завершения
            if audio_input_task and not audio_input_task.done():
                audio_input_task.cancel()
            if recognition_task and not recognition_task.done():
                recognition_task.cancel()
            
            # Собираем результаты отмененных задач, чтобы обработать CancelledError
            # и дать им время на очистку в блоках finally
            # await asyncio.gather(audio_input_task, recognition_task, return_exceptions=True)
            # Более безопасный способ дождаться отмены:
            all_tasks = asyncio.all_tasks(asyncio.get_running_loop())
            tasks_to_wait = [t for t in all_tasks if t is not asyncio.current_task()]
            if tasks_to_wait:
                await asyncio.wait(tasks_to_wait)


            self.audio_in.stop_capture() # Это должно разблокировать get_data, если он ждет
            await self.shutdown_systems()
            log.info("VoiceAssistant: Приложение завершило работу.")

    async def shutdown_systems(self):
        # ... остановка других сервисов ...
        if self.tts_service:
            await self.tts_service.destroy()
        log.info("Сервис синтеза речи остановлен.")
    
    # ... (shutdown_systems и другие методы) ...