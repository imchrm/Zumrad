# main_application.py
from typing import Any, Optional, Callable, Coroutine
import asyncio
from pydub import AudioSegment
from pydub.playback import play
import logging
from tempfile import NamedTemporaryFile
import subprocess
from zumrad_iis import config # Используем относительный импорт, если main.py часть пакета zumrad_iis
from zumrad_iis.services.audio_input_service import AudioInputService
from zumrad_iis.services.avosk_stt import STTService # Импортируем конфигурацию
from zumrad_iis.core.tts_interface import TextToSpeechInterface
from zumrad_iis.services.stt.speech_recognizer import SpeechRecognizer
from zumrad_iis.tts_implementations.async_silero_tts import AsyncSileroTTS
from zumrad_iis.services.activation_service import ActivationService
from zumrad_iis.services.command_service import CommandService
from zumrad_iis.services.external_process_service import ExternalProcessService
# from services import AudioInputService, SpeechRecognitionService, ...
import zumrad_iis.commands.handlers.process_commands as process_commands # Импортируем обработчики команд
import zumrad_iis.commands.handlers.system_commands as system_commands # Импортируем системные команды

log = logging.getLogger(__name__) 

class VoiceAssistant:
    
    _IS_WAIT_FOR_RECOGNITION_TASK: bool = True  # Флаг для управления способом распознавания
    
    def __init__(self):
        # Загрузка конфигурации
        self.config = config
        # Инстанцирование сервисов
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
        
        self.speech_recognizer = SpeechRecognizer(
            audio_in = self.audio_in,
            stt = self.stt,
            recognized_text_handler = self._process_recognized_text,
            stop_handler = self._handle_recognition_stop
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

        # Состояние ассистента
        self._is_repit = False # Режим повторения фразы
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
        log.debug(f"Playing sound: {sound_path}")
        # Fix of `PermissionError: [Errno 13] Permission denied` issue when using pydub for plaing temp audio files under Windows`
        # https://github.com/jiaaro/pydub/issues/209
        # This is changed method from pydub.playback 
        PLAYER = "ffplay"
        def _play_with_ffplay(seg: AudioSegment, player:str):
             
            with NamedTemporaryFile("w+b", suffix=".wav") as f:
                f.close() # close the file stream
                seg.export(f.name, "wav")
                subprocess.call([player, "-nodisp", "-autoexit", "-hide_banner", f.name])
            
        try:
            # Загружаем аудиофайл с помощью pydub
            sound = AudioSegment.from_file(sound_path)
            # Воспроизводим его в отдельном потоке, чтобы не блокировать asyncio
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _play_with_ffplay, sound, PLAYER)
        except Exception as e:
            log.error(f"Не удалось воспроизвести звук {sound_path} с помощью {PLAYER}: {e}")

    def _setup_commands(self):
        self.command_service.register_command("запусти видеоплеер", process_commands.launch_videoplayer)
        self.command_service.register_command("сколько времени", system_commands.what_time_is_it)
        self.command_service.register_command("повторяй", self._trigger_repite_that)
        self.command_service.register_command("стоп", self._trigger_repite_that)
        # ... и так далее
        pass
    
    def _trigger_repite_that(self):
        self._is_repit = not self._is_repit
    
    async def initialize_systems(self):
        self._setup_commands() # Зарегистрируем команды
        # ... инициализация других систем ...
        await self.speech_recognizer.initialize() # Инициализация SpeechRecognizer
        # await self.stt.initialize() # Инициализация STT

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

    # TODO: нужно подумать над улучшением обработки команд в этом методе, чтобы она стала более гибкой.
    async def _process_recognized_text(self, recognized_text: str):
        """
        Эта корутина выполняется в основном цикле asyncio и обрабатывает распознанный текст.
        """
        log.info(f"MainLoop CB <<: {recognized_text}")

        if self._check_is_exit_phrase(recognized_text):
            log.info("VoiceAssistant: Завершение работы по команде выхода...")
            await self.say("Завершаю работу.", voice=self.config.TTS_VOICE)
            # self.is_running = False # Сигнал для остановки всех циклов
            await self.speech_recognizer.stop() # Останавливаем распознавание речи
            return
        
        if self._is_repit:
            self.speech_recognizer.pause()
            log.debug("Pause Speech Recognition")
            await self.say(recognized_text)
            self.speech_recognizer.resume()
            log.debug("Resume Speech Recognition")
            
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
        
        # Передаем цикл событий в сервисы, которым он необходим для
        # потокобезопасного взаимодействия с asyncio из других потоков.
        self.audio_in.set_event_loop(self._main_event_loop)
        self.speech_recognizer.set_event_loop(self._main_event_loop)
        
        await self.initialize_systems()
        
        try:
            await self.speech_recognizer.start()
        except asyncio.CancelledError:
            # Этот блок сработает, если сама корутина run() будет отменена извне
            # (например, при нажатии Ctrl+C в asyncio.run()). Это штатная ситуация.
            log.info("Основная задача 'run' была отменена. Завершение работы.")
        except Exception as e:
            # speech_recognizer.start() теперь сам обрабатывает свои ошибки, но если
            # ошибка произойдет до его запуска или после, мы ее поймаем здесь.
            log.exception(f"В VoiceAssistant.run произошла критическая ошибка: {e}")
        finally:
            # Этот блок гарантирует, что stop будет вызван, даже если speech_recognizer.start()
            # завершится с ошибкой до своего собственного блока finally.
            await self.speech_recognizer.stop()
    
    async def _handle_recognition_stop(self):
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
        level=logging.DEBUG, # или config.LOG_LEVEL
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    assistant = VoiceAssistant()
    # Основная логика запуска. Обработка исключений перенесена на уровень выше.
    await assistant.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Эти исключения являются ожидаемыми при штатном завершении.
        # Логируем как info и выходим.
        log.info("Приложение успешно остановлено пользователем.")
    except Exception as e:
        log.critical(f"Критическая ошибка на верхнем уровне приложения: {e}", exc_info=True)