import asyncio
import logging
from typing import Optional, Any, Protocol, cast, Dict, List
import sounddevice as sd
import torch
import functools
from zumrad_iis.core.tts_interface import ITextToSpeech
# zumrad_app/core/tts_interface.py

log: logging.Logger = logging.getLogger(__name__)

# --- Протокол модели ---
class TTSModelProtocol(Protocol):
    """
    Протокол для модели TTS, чтобы гарантировать наличие нужных методов.
    Для чего нужен этот протокол?
    Метод `torch.hub.load`, ниже, декларирует, что возвращает простой `object`(-> object), но при этом возвращает `tuple` (кортеж), 
    в котором первый элемент - это наша модель TTS у которой должны быть методы `to` и `apply_tts`.
    Чтобы Pylint мог проверить, что загруженный объект соответствует ожидаемому интерфейсу.
    Используется для статической типизации и проверки совместимости.
    """
    def to(self, device: Any) -> None: 
        ... # Protocol использует ... для обозначения абстрактных методов без реализации
    def apply_tts(self, 
                text: str,
                speaker: str,
                sample_rate: int,
                put_accent: bool,
                put_yo: bool,
                **kwargs: Any) -> torch.Tensor: 
        ... 


class AsyncSileroTTS(ITextToSpeech):
    """
    Класс для работы с Silero TTS в асинхронном контексте.
    Позволяет асинхронно загрузить иинициализировать модель.
    Позволяет синтезировать речь.
    :param language: Язык модели (например, 'ru', 'uz').
    :param model_id: Идентификатор модели (например, 'v3_1_ru', 'v4_uz').
    :param sample_rate: Частота дискретизации аудио (например, 48000, 24000, 16000, 8000).
    :param device: Устройство для выполнения модели (например, 'cpu' или 'cuda').
    :raises ValueError: Если частота дискретизации не поддерживается. 
    """

    def __init__(self,
            language: str,
            model_id: str,
            sample_rate: int,
            device: Optional[torch.device] = None,
            ) -> None:
        self.language: str = language
        self.model_id: str = model_id
        if sample_rate not in [48000, 24000, 16000, 8000]:
            raise ValueError(f"Неподдерживаемая частота дискретизации: {sample_rate}. "
                            "Допустимы значения: 48000, 24000, 16000, 8000.")
        else:
            self.sample_rate: int = sample_rate
        
        self.device = torch.device('cpu') if device is None else device
        
        # --- Глобальная переменная для кэширования модели ---
        self._model: Optional[TTSModelProtocol] = None
        # Флаг для предотвращения одновременного запуска нескольких задач загрузки
        self._model_initialization_task: Optional[asyncio.Task] = None
        # Lock to prevent concurrent initializations
        self._init_lock = asyncio.Lock() 
            
            
    def _blocking_load_and_init_model(self) -> Optional[TTSModelProtocol]:
        """
        Синхронная (блокирующая) часть загрузки и инициализации модели.
        Эта функция будет выполняться в отдельном потоке через asyncio.to_thread.
        """
        log.debug("Блокирующая загрузка и инициализация модели Silero TTS в потоке...")
        try:
            loaded_artifact = torch.hub.load(
                repo_or_dir='snakers4/silero-models',
                model='silero_tts',
                language=self.language,
                speaker=self.model_id,
                trust_repo=True
            )
            # Метод `torch.hub.load`, выше, декларирует, что возвращает простой `object`, но при этом возвращает `tuple`, 
            # в котором первый элемент - это наша модель TTS у которой должны быть методы `to` и `apply_tts`.
            # Поэтому делаем универсальный подход к получению модели:
            # Если это кортеж (tuple), то берем первый элемент, иначе - сам объект
            actual_model_candidate: Any
            if isinstance(loaded_artifact, tuple):
                actual_model_candidate = loaded_artifact[0]
            else:
                actual_model_candidate = loaded_artifact

            if (hasattr(actual_model_candidate, 'to') and
                hasattr(actual_model_candidate, 'apply_tts')):
                # explicit cast to TTSModelProtocol
                typed_model: TTSModelProtocol = cast(TTSModelProtocol, actual_model_candidate)
                # typed_model: TTSModelProtocol = actual_model_candidate
                typed_model.to(self.device)
                log.debug("Модель Silero TTS успешно загружена и инициализирована в потоке.")
                return typed_model
            else:
                log.debug(f"Ошибка в потоке: Загруженный артефакт типа {type(actual_model_candidate)} не соответствует протоколу.")
                return None
        
        except Exception as e:
            log.debug(f"Исключение в потоке при загрузке или инициализации модели TTS: {e}")
            return None


    async def load_and_init_model(self, config:Optional[Dict[str, Any]] = None) -> bool:
        """
        Асинхронно загружает и инициализирует модель Silero TTS.
        Этот метод дождется завершения загрузки перед возвратом.
        Возвращает True, если модель успешно загружена и готова, иначе False.
        """
        async with self._init_lock:
            if self._model is not None:
                # Модель TTS уже загружена.
                return True
            
            # Создаем задачу, которая будет выполняться в фоновом режиме
            # В данной реализации этот враппер не нужен, так как мы ожидаем результат здесь же, ниже.
            async def _task_wrapper() -> Optional[TTSModelProtocol]:
                # global loaded_silero_model, model_initialization_task # Для изменения внешней переменной из замыкания
                model: Optional[TTSModelProtocol] = None
                try:
                    # Выполняем блокирующую функцию в отдельном потоке, управляемом asyncio
                    # Для Python >=3.9
                    if hasattr(asyncio, 'to_thread'):
                        model = await asyncio.to_thread(self._blocking_load_and_init_model)
                    else:
                        # Для Python < 3.9
                        # loop = asyncio.get_event_loop()
                        loop = asyncio.get_running_loop()
                        model = await loop.run_in_executor(None, self._blocking_load_and_init_model)
                    
                except Exception as e:
                    log.debug(f"Исключение внутри _task_wrapper при инициализации модели: {e}")
                    # Ensure 'model' is None if an exception occurs during the loading process.
                    model = None 
                finally:
                    self._model_initialization_task = None # Сбрасываем задачу после завершения (успешного или нет)
                    
                return model

            # Если асинхронная инициализация, запускаем задачу в фоне и ожидаем ее завершения
            log.info("Ожидаем загрузку модели в фоне...")
            try:
                self._model_initialization_task = asyncio.create_task(_task_wrapper())
                # Дожидаемся завершения задачи и получаем модель
                # В принципе `self._model_initialization_task` не нужна, она имела бы смысл,
                # если бы мы не ожидали ее результата здесь, а вернули бы флаг, что задача запущена, при этом модель была бы не загружена. 
                self._model = await self._model_initialization_task 
            except Exception as e:
                log.debug(f"Ошибка при запуске асинхронной задачи инициализации модели: {e}")
                self._model_initialization_task = None
            finally:
                if self._model is None:
                    log.warning("Ошибка: Модель TTS не была инициализирована.")
            
            return self._model is not None

    # --- Функция синтеза речи (остается синхронной, но проверяет асинхронно загруженную модель) ---
    # или ее тоже можно сделать асинхронной, если sd.play/wait могут быть проблемой
    async def speak(self, text: str, voice: str | None = None) -> bool:
        if voice is None:
            raise ValueError("To call the speech synthesis function (TTS), you must specify the `speaker_voice` argument.")
        
        if self._model is None:
            raise RuntimeError("Модель TTS не инициализирована. "
                            "Пожалуйста, сначала вызовите `load_and_init_model()` и дождитесь завершения инициализации.")
                
        log.debug(f"Speech synthesis (asynchronous context) for: '{text}'...")
        try:
            audio: torch.Tensor = self._model.apply_tts(text=text + ".s...",
                                                speaker=voice,
                                                sample_rate=self.sample_rate,
                                                put_accent=True,
                                                put_yo=True)
            
            audio_numpy = audio.cpu().numpy()

            def _play_and_wait_sync():
                """
                Блокирующая функция, которая запускает воспроизведение и ждет его окончания.
                Именно эту единую функцию нужно выполнять в отдельном потоке.
                """
                sd.play(audio_numpy, samplerate=self.sample_rate)
                sd.wait()

            loop = asyncio.get_running_loop()
            if hasattr(asyncio, 'to_thread'): 
                # Для Python >=3.9
                await asyncio.to_thread(_play_and_wait_sync)
            else: 
                # Для Python < 3.9
                await loop.run_in_executor(None, _play_and_wait_sync)
                
            log.info("Воспроизведение завершено (асинхронный контекст).")
            return True
        except Exception as e:
            log.debug(f"Ошибка при синтезе или воспроизведении речи (асинхронный контекст): {e}")
            return False
        
    async def is_ready(self) -> bool:
        return self._model is not None
        
    async def destroy(self) -> None:
        self._model = None
        

if __name__ == '__main__':
    
    async_tts:AsyncSileroTTS
    
    phrases:Dict[str, List[tuple[str, str]]] = {
        "ru": [
            ("Привет из асинхронного мира!", "kseniya"),
            ("Я - робот В+ертер. Кожанный мешок, слушаю тебя.", "aidar")
        ],
        "uz": [
            ("Ish ishtaha ochar, dangasa ishdan qochar.-", "dilnavoz"),
            ("Aql yoshda emas, boshda.-","dilnavoz"),
            ("Bosh omon bo'lsa, do'ppi topiladi.-", "dilnavoz"),
        ]
    }
    # Определяем язык и модель для тестирования
    test_language = "uz"
    
    if test_language == "uz":
        async_tts = AsyncSileroTTS(language="uz", model_id="v4_uz", sample_rate=48000)
    elif test_language == "ru":
        async_tts = AsyncSileroTTS(language="ru", model_id="v3_1_ru", sample_rate=48000)
    else:
        raise ValueError(f"Unsupported language: {test_language}")
    
    # Запускаем главный асинхронный цикл
    
    # --- Пример использования в асинхронном приложении ---
    async def main_async(asilero_tts: AsyncSileroTTS):
        """
        Главная асинхронная функция, которая демонстрирует использование асинхронной инициализации TTS.
        """
        log.info("Запуск асинхронной инициализации TTS...")
        # Запускаем инициализацию, но не обязательно ждем ее здесь,
        # если другие части приложения могут работать параллельно.
        init_started = await asilero_tts.load_and_init_model()
        if not init_started: # Это проверит только запуск задачи, а не готовность модели
            log.warning("Failed to start TTS initialization task.")
            raise Exception("Failed to start TTS initialization task.")
            # return # Или другая обработка

        log.info("Инициализация TTS запущена. Продолжение работы основной программы...")
        
        # Эмулируем другую работу приложения
        # for i in range(5):
        #     print(f"Основное приложение работает... ({i+1}/5)")
        #     await asyncio.sleep(0.5) # Неблокирующая пауза

        # Теперь пытаемся использовать TTS
        # synthesize_speech_async сама дождется завершения инициализации, если нужно.
        for phrase in phrases[test_language]:
            await asilero_tts.speak(phrase[0], voice=phrase[1])
            # await asyncio.sleep(1)
        
        # await asilero_tts.speak("Привет из асинхронного мира!", speaker_voice='kseniya')
        # await asyncio.sleep(1)
        # await asilero_tts.speak("Я - робот В+ертер. Слушаю вас, кожанные мешки.", speaker_voice='aidar')
    
    try:
        asyncio.run(main_async(async_tts))
    except KeyboardInterrupt:
        log.warning("\nПрограмма прервана пользователем.")
    finally:
        # Здесь можно добавить корректное закрытие ресурсов, если необходимо
        # Например, дождаться завершения model_initialization_task, если оно еще работает
        # и мы хотим чистого выхода.
        if async_tts._model_initialization_task and not async_tts._model_initialization_task.done():
            log.info("Ожидание завершения фоновой задачи инициализации TTS перед выходом...")