# main_application.py
from typing import Optional
import asyncio
import logging
import functools
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
        
        self._run_in_thread_lock = asyncio.Lock()  # Блокировка для управления доступом к run()
        self._run_in_thread_task : Optional[asyncio.Task] = None  # Задача, которая будет выполняться в отдельном потоке

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
        
        await self.stt.initialize() # Инициализация STT
        
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
            print(f"ASSISTANT (fallback): {text}") # Запасной вариант вывода
    
    async def run(self):
        log.info("VoiceAssistant: Запуск основного цикла...")
        await self.initialize_systems() # Инициализируем TTS и другие системы

        # log.info(f"Доступные устройства для захвата голоса: {sd.query_devices()}")
        # log.info(f"Используется устройство: {sd.query_devices(self.config.DEVICE_ID, 'input')}")

        self.audio_in.start_capture()
        log.info("Говорите. Для остановки нажмите Ctrl+C")
        self.is_running = True
        try:
            while self.is_running:
                # get_data() блокирующий, для асинхронного выполнения его нужно запускать в executor
                # или AudioInputService должен предоставлять асинхронный интерфейс
                try:
                    loop = asyncio.get_running_loop()
                    # Вызываем блокирующий get_data в executor.
                    # Это будет ждать, пока в очереди появятся данные или sentinel (None).
                    audio_data = await loop.run_in_executor(
                        None,
                        self.audio_in.get_data
                    )
                    if audio_data is None:
                        # get_data вернуло None - это наш сигнал остановки
                        log.info("VoiceAssistant: Получен сигнал остановки из очереди аудио.")
                        break # Выходим из цикла while self.is_running
                except Exception as e:
                    # This catch block is less likely now, as queue.Empty is handled inside get_data
                    # Ловим другие возможные ошибки из run_in_executor или get_data
                    log.error(f"VoiceAssistant: Ошибка при получении аудиоданных: {e}")
                    # await asyncio.sleep(0.1) # Пауза при ошибке
                    continue
                
                recognized_text = await loop.run_in_executor(None,self.stt.transcribe, audio_data)

                if not recognized_text:
                    continue

                log.info(f">>: {recognized_text}")
                continue
                if self._check_is_exit_phrase(recognized_text):
                    log.info("VoiceAssistant: Завершение работы по команде выхода...")
                    await self.say("Завершаю работу.", voice=config.TTS_VOICE)
                    self.is_running = False
                    break

                if self.activation_service.is_active():
                    # TODO: Добавить проверку на повторное ключевое слово, если нужно
                    # if self.activation_service.is_keyword_again(recognized_text): ...

                    command_executed = self.command_service.execute_command(recognized_text)
                    if command_executed:
                        log.info(f"VoiceAssistant: Команда '{recognized_text}' выполнена.")
                        await self._play_feedback_sound(config.COMMAND_SOUND_PATH)
                        self.activation_service.deactivate()
                        self.audio_in.clear_queue()
                        # self.stt.reset() # Vosk сбрасывается при каждом Result, если AcceptWaveform вернул True
                    else:
                        log.warning(f"VoiceAssistant: Команда не распознана: {recognized_text}")
                        # await self.say("Команда не распознана.", voice=config.TTS_VOICE) # Опционально
                else: # Система не активирована
                    processed_text_after_keyword = self.activation_service.check_and_trigger_activation(recognized_text)
                    if self.activation_service.is_active(): # Если только что активировалась
                        await self._play_feedback_sound(config.ACTIVATION_SOUND_PATH)
                        self.audio_in.clear_queue()
                        # self.stt.reset()

                        if processed_text_after_keyword:
                            log.info(f"VoiceAssistant: Команда после активации: {processed_text_after_keyword}")
                            command_executed = self.command_service.execute_command(processed_text_after_keyword)
                            if command_executed:
                                await self._play_feedback_sound(config.COMMAND_SOUND_PATH)
                                self.activation_service.deactivate()
                                self.audio_in.clear_queue()
                            else:
                                log.warning(f"VoiceAssistant: Команда после активации не распознана: {processed_text_after_keyword}")
                                # await self.say("Команда не ясна.", voice=config.TTS_VOICE)
                                # Остаемся активными, ждем следующую команду
                        else:
                            log.info(f"VoiceAssistant: Ключевое слово '{config.STT_KEYWORD}' распознано! Жду вашу команду...")
                            # await self.say("Слушаю.", voice=config.TTS_VOICE)
                # await asyncio.sleep(0.01) # Даем другим задачам шанс выполниться

        except KeyboardInterrupt:
            log.info("\nVoiceAssistant: Завершение работы по Ctrl+C...")
            self.is_running = False
        except Exception as e: # Более общая обработка ошибок
            log.exception(f"VoiceAssistant: Произошла критическая ошибка: {e}")
            self.is_running = False
        finally:
            self.audio_in.stop_capture()
            # if self.processes.is_running(): # Метод для проверки, запущен ли какой-то процесс
            #    self.processes.terminate()
            await self.shutdown_systems()
            log.info("VoiceAssistant: Приложение завершило работу.")
            
    async def _speech_recognition_thread(self, callback=None):
        """
        Запускает поток для распознавания речи.
        Этот метод должен быть вызван в отдельном потоке, чтобы не блокировать основной цикл.
        """
        try:
            while self.is_running:
                audio_data = self.audio_in.get_data()
                if audio_data is None:
                    continue  # Если нет данных, продолжаем цикл

                recognized = self.stt.transcribe(audio_data)
                if recognized:
                    log.info(f"Распознано: {recognized}")
                    # здесь вызов callback с передачей распознанного текста
                    # Здесь можно добавить логику обработки распознанного текста
                    # Например, передать в командный сервис или выполнить другие действия
                else:
                    pass
                    # log.debug("Распознавание не удалось, ждем следующую порцию аудио.")
        except Exception as e:
            log.error(f"VoiceAssistant: Ошибка в потоке распознавания речи: {e}")
                    
    async def run_in_thread(self, func, *args, **kwargs):
        async with self._run_in_thread_lock:
            
            async def _task_wrapper() -> Optional[bool]:
                await asyncio.to_thread(self._speech_recognition_thread)  # Запускаем поток распознавания речи
                return True
            try:
                self._run_in_thread_task = asyncio.create_task(_task_wrapper())
                
            except asyncio.CancelledError:
                log.info("VoiceAssistant: Задача была отменена.")
                return
            except Exception as e:
                log.error(f"VoiceAssistant: Ошибка при запуске задачи в потоке: {e}")
                return
    
    async def shutdown_systems(self):
        # ... остановка других сервисов ...
        if self.tts_service:
            await self.tts_service.destroy()
        log.info("Сервис синтеза речи остановлен.")

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