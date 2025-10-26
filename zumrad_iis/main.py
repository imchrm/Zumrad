# main_application.py
from typing import Any, Optional, Callable, Coroutine, TYPE_CHECKING, Type
import asyncio
from pydub import AudioSegment
from pydub.playback import play
import logging
from tempfile import NamedTemporaryFile
import subprocess
from zumrad_iis import config # Используем относительный импорт, если main.py часть пакета zumrad_iis
import sounddevice as sd
from zumrad_iis.commands.command_processor import CommandExecutor, CommandProcessor, CommandRunner, CommandTranslator
from zumrad_iis.commands.command_vocabulary import CommandVocabulary
from zumrad_iis.commands.register.speak import AttentionOneCommand, SpeakCommand
from zumrad_iis.commands.register.repeat_phrases import RepeatPhrasesCommand
from zumrad_iis.commands.register.what_time_is_it import WhatTimeIsItCommand
from zumrad_iis.services.audio_feedback_service import AudioFeedbackService
from zumrad_iis.services.audio_input_service import AudioInputService
from zumrad_iis.services.avosk_stt import STTService # Импортируем конфигурацию
from zumrad_iis.core.tts_interface import ITextToSpeech
from zumrad_iis.services.stt.speech_recognizer import SpeechRecognizer
from zumrad_iis.tts_implementations.async_silero_tts import AsyncSileroTTS
from zumrad_iis.services.activation_service import ActivationService
from zumrad_iis.services.command_service import CommandService
from zumrad_iis.services.external_process_service import ExternalProcessService
# from services import AudioInputService, SpeechRecognitionService, ...
import zumrad_iis.commands.handlers.process_commands as process_commands # Импортируем обработчики команд
import zumrad_iis.commands.handlers.system_commands as system_commands # Импортируем системные команды

log: logging.Logger = logging.getLogger(__name__) 

if TYPE_CHECKING:
    from . import config as config_module_type

from colorama import Back, Fore, Style, init
from colorama import just_fix_windows_console
just_fix_windows_console()
init(autoreset=True)

class VoiceAssistant:
    
    _IS_WAIT_FOR_RECOGNITION_TASK: bool = True  # Флаг для управления способом распознавания
    
    def __init__(self) -> None:
        # Загрузка конфигурации
        # self.config: "config_module_type" = config_module
        # Инстанцирование сервисов

        self.audio_in: AudioInputService = AudioInputService(
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
            ready_handler = self.speech_recognizer_ready_handler,
            recognized_text_handler = self._process_recognized_text,
            stop_handler = self._handle_recognition_stop
        )

        self.tts_service: ITextToSpeech = AsyncSileroTTS(
            language = config.TTS_LANGUAGE, # Используем config
            model_id = config.TTS_MODEL_ID, # Используем config
            sample_rate = config.TTS_SAMPLERATE, # Используем config
            
            # device=torch.device(config.TTS_DEVICE) # Если нужно передавать torch.device
        )

        self.activation_service = ActivationService(config.STT_KEYWORD)
        # self.command_service = CommandService()
        self.command_processor = CommandProcessor(
            CommandExecutor(
                AudioFeedbackService(config.COMMAND_SOUND_PATH)), 
                CommandTranslator(vocabulary = config.command_vocabulary))

        # self.feedback = AudioFeedbackService()
        self.external_processes_service = ExternalProcessService()

        # Состояние ассистента
        self._is_repeat = False # Режим повторения фразы
        self.is_running = True  # Флаг для управления основным циклом
        self._main_event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._recognition_task: Optional[asyncio.Task] = None

    # Вспомогательные методы, перенесенные и адаптированные из a_main.py
    def _check_is_exit_phrase(self, text: str) -> bool:
        cmd: str | None = config.command_vocabulary.vocabulary_map.get(text)
        return cmd is not None and cmd == config.CMD_QUIT
    
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
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _play_with_ffplay, sound, PLAYER)
        except Exception as e:
            log.error(f"Не удалось воспроизвести звук {sound_path} с помощью {PLAYER}: {e}")

    def _setup_commands(self) -> None:

        # self.command_service.register_command("запусти видеоплеер", process_commands.launch_video_player)
        # self.command_service.register_command("сколько времени", system_commands.what_time_is_it)
        self.command_processor.register_command(
            config.CMD_WHAT_TIME_IS_IT, WhatTimeIsItCommand()
        )
        self.command_processor.register_command(
            config.CMD_REPEAT_ON, RepeatPhrasesCommand(self._set_repeat_mode, True)
        )
        self.command_processor.register_command(
            config.CMD_REPEAT_OFF, RepeatPhrasesCommand(self._set_repeat_mode, False)
        )
        self.command_processor.register_command(
            config.CMD_ATTENTION_ONE, SpeakCommand(
                self.tts_service, config.interactive_dictionary[
                    config.CMD_ATTENTION_ONE], config.TTS_VOICE
            )
        )
        self.command_processor.register_command(
            config.CMD_ATTENTION_TWO, SpeakCommand(
                self.tts_service, config.interactive_dictionary[
                    config.CMD_ATTENTION_TWO], config.TTS_VOICE
            )
        )
        # self.command_service.register_command("повторяй", self._trigger_repeat_that)
        # self.command_service.register_command("стоп", self._trigger_repeat_that)
        # ... и так далее
        pass

    def _set_repeat_mode(self, is_repeat: bool) -> None:
        self._is_repeat = is_repeat

    def _trigger_repeat_that(self):
        self._is_repeat: bool = not self._is_repeat
    
    async def initialize_systems(self) -> None:
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

    def speech_recognizer_ready_handler(self) -> None:
        gp: str | None = config.interactive_dictionary.get("greeting")
        if(gp):
            ps: list[str] = gp.split("{activation.keyword}")
            print(Fore.RED + Back.YELLOW + Style.BRIGHT +f"{ps[0]}{config.STT_KEYWORD.capitalize()}{ps[1]}")

    # TODO: нужно подумать над улучшением обработки команд в этом методе, чтобы она стала более гибкой.
    async def _process_recognized_text(self, recognized_text: str):
        """
        Эта корутина выполняется в основном цикле asyncio и обрабатывает распознанный текст.
        """
        log.debug(f"MainLoop CB <<: {recognized_text}")
        
        if self._check_is_exit_phrase(recognized_text):
            log.debug("VoiceAssistant: Terminating work on exit command...")
            phrase_quit: str | None = config.interactive_dictionary.get(config.ITR_QUIT)
            if phrase_quit:
                await self.say(phrase_quit, voice=config.TTS_VOICE)
                # self.is_running = False # Сигнал для остановки всех циклов
                await self.speech_recognizer.stop() # Останавливаем распознавание речи
            return
        
        if self._is_repeat:
            self.speech_recognizer.pause()
            log.debug("Pause Speech Recognition")
            await self.say(recognized_text)
            # Добавляем небольшую паузу, чтобы аудиодрайвер успел освободить устройство перед возобновлением захвата.
            await asyncio.sleep(0.1)
            self.speech_recognizer.resume()
            log.debug("Resume Speech Recognition")
        is_command_was_executed: bool = False  
        if self.activation_service.is_active():
            # Если self.command_service.execute_command может быть долгим,
            # его также стоит запускать через await asyncio.to_thread(...)
            # command_executed: bool = self.command_service.execute_command(recognized_text)
            is_command_was_executed = await self.command_processor.process(recognized_text)
            if is_command_was_executed:
                log.info(f"VoiceAssistant: Команда '{recognized_text}' выполнена.")
                print(Fore.BLUE + Back.GREEN + Style.BRIGHT + 
                      f"{config.interactive_dictionary[config.ITR_COMMAND_IS_DEFINED]} [{recognized_text}]")
                self.activation_service.deactivate()
                self.audio_in.clear_queue()
            else:
                log.warning(f"Command is undefined: {recognized_text}")
                print(Fore.GREEN + Back.RED + Style.BRIGHT + 
                      f"{config.interactive_dictionary[config.ITR_COMMAND_IS_UNDEFINED]} [{recognized_text}]")
                # await self.say("Команда не распознана.", voice=config.TTS_VOICE)
        else: # Система не активирована
            processed_text_after_keyword: str | None = \
                self.activation_service.check_and_trigger_activation(recognized_text)
            
            if self.activation_service.is_active(): # Если только что активировалась
                await self._play_feedback_sound(config.ACTIVATION_SOUND_PATH)
                self.audio_in.clear_queue()

                if processed_text_after_keyword:
                    log.info(f"VoiceAssistant: Команда после активации: {processed_text_after_keyword}")
                    # command_executed = self.command_service.execute_command(processed_text_after_keyword)
                    
                    is_command_was_executed = await self.command_processor.process(processed_text_after_keyword)
                    if is_command_was_executed:
                        print(Fore.BLUE + Back.GREEN + Style.BRIGHT + 
                            f"{config.interactive_dictionary[config.ITR_COMMAND_IS_DEFINED]} [{processed_text_after_keyword}]")
                        self.activation_service.deactivate()
                        self.audio_in.clear_queue()
                    else:
                        log.warning(f"Command is undefined after activation: {processed_text_after_keyword}")
                        print(Fore.GREEN + Back.RED + Style.BRIGHT + 
                            f"{config.interactive_dictionary[config.ITR_COMMAND_IS_UNDEFINED]} [{processed_text_after_keyword}]")
                        # await self.say("Команда не ясна.", voice=config.TTS_VOICE)
                        # Остаемся активными, ждем следующую команду
                else:
                    log.info(f"VoiceAssistant: Ключевое слово '{config.STT_KEYWORD}' распознано! Жду вашу команду...")
                    # await self.say("Слушаю.", voice=config.TTS_VOICE)

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
    # 1. Загружаем конфигурацию из файла.
    config.load_and_apply_config()

    # 2. Устанавливаем глобальные настройки для sounddevice, чтобы избежать конфликтов
    # между потоками ввода и вывода. Это решает проблему "проглатывания" звука.
    sd.default.samplerate = config.TTS_SAMPLERATE  # type: ignore
    sd.default.channels = config.STT_CHANNELS      # type: ignore
    log.info(f"Для стабильности работы все аудиопотоки будут использовать единую частоту: {sd.default.samplerate} Гц")

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