# zumrad_app/core/tts_engine.py (или tts_implementations/silero_tts.py)
import torch
import logging
import sounddevice as sd
import asyncio
from typing import Optional, Dict, Any, Protocol, List, cast

# Импортируем наш интерфейс
from zumrad_iis.core.tts_interface import ITextToSpeech # Если tts_interface.py в той же папке (core)

log = logging.getLogger(__name__) 

class DefaulSpeechModelConfig:
    """
    Конфигурация по умолчанию для языков.
    Можно расширить, если нужно поддерживать больше языков.
    """
    LANGUAGE = 'ru'
    MODEL_ID = 'v3_1_ru'
    SAMPLE_RATE = 48000
    DEVICE = 'cpu'


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

class AsyncSileroTTS(ITextToSpeech): # <--- Указываем, что реализуем интерфейс
    """
    Асинхронная реализация TTS на основе Silero.
    Использует torch.hub для загрузки модели и sounddevice для воспроизведения аудио.
    Поддерживает асинхронную инициализацию и воспроизведение.
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
                ):
        self.language = language
        self.model_id = model_id
        if sample_rate not in [48000, 24000, 16000, 8000]:
            raise ValueError(f"Not supported sample rate: {sample_rate}. "
                            "Acceptable values: 48000, 24000, 16000, 8000.")
        else:
            self.sample_rate = sample_rate
        
        self.device = torch.device(DefaulSpeechModelConfig.DEVICE) if device is None else device
        
        self._model:Optional[TTSModelProtocol] = None
        self._is_initialized = False

    async def load_and_init_model(self, config: Optional[Dict[str, Any]] = None) -> bool:
        if self._is_initialized:
            return True
        
        log.info("AsyncSileroTTS: Инициализация Silero модели...")
        # Переопределяем конфигурацию, если она передана
        if config:
            self.language = config.get("language", DefaulSpeechModelConfig.LANGUAGE)
            self.model_id = config.get("model_id", DefaulSpeechModelConfig.MODEL_ID)
            self.sample_rate = config.get("sample_rate", DefaulSpeechModelConfig.SAMPLE_RATE)
            # DEVICE можно тоже конфигурировать, но обычно CPU для TTS
        
        try:
            # Загрузка модели (как ты делал раньше, возможно, в _loop.run_in_executor для неблокировки)
            # Этот код блокирующий, для настоящего async его нужно адаптировать
            def _load_model_sync() -> Optional[TTSModelProtocol]:
                
                actual_model_candidate: Any = None
                typed_model: TTSModelProtocol
                
                loaded_artifact = torch.hub.load(
                    repo_or_dir='snakers4/silero-models',
                    model='silero_tts',
                    language=self.language,
                    speaker=self.model_id,
                    trust_repo=True
                )
                log.debug(f"AsyncSileroTTS: Загруженный артефакт: {type(loaded_artifact)}")
                if isinstance(loaded_artifact, tuple):
                    actual_model_candidate = loaded_artifact[0]
                else:
                    actual_model_candidate = loaded_artifact

                if (hasattr(actual_model_candidate, 'to') and
                    hasattr(actual_model_candidate, 'apply_tts')):
                    # explicit cast to TTSModelProtocol
                    typed_model = cast(TTSModelProtocol, actual_model_candidate)
                    # typed_model: TTSModelProtocol = actual_model_candidate
                    typed_model.to(self.device)  # Перемещаем модель на нужное устройство
                    log.info("Модель Silero TTS успешно загружена и инициализирована в потоке.")
                    return typed_model
                else:
                    log.info(f"Ошибка в потоке: Загруженный артефакт типа {type(actual_model_candidate)} не соответствует протоколу.")
                    return None

            # Выполняем блокирующую загрузку в отдельном потоке, чтобы не блокировать asyncio event loop
            log.debug("AsyncSileroTTS: Блокирующая загрузка модели...")
            if hasattr(asyncio, 'to_thread'):
                # Если есть to_thread, используем его для асинхронного вызова
                self._model = await asyncio.to_thread(_load_model_sync)
            else:
                loop = asyncio.get_running_loop()
                # self._model = await asyncio.get_event_loop().run_in_executor(None, _load_model_sync)
                self._model = await loop.run_in_executor(None, _load_model_sync)
            log.info(f"AsyncSileroTTS: Модель загружена: {self._model is not None}, тип: {type(self._model)}")
            if self._model is not None:
                self._is_initialized = True
                log.info("AsyncSileroTTS: Модель успешно загружена.")
                # return True
            else:
                log.info("AsyncSileroTTS: Не удалось загрузить модель.")
                # return False
        except Exception as e:
            log.info(f"AsyncSileroTTS: Ошибка при инициализации модели: {e}")
            # return False
        return self._is_initialized


    async def speak(self, text: str, voice: Optional[str] = None, **kwargs) -> bool:
        if voice is None:
            raise ValueError("To call the speech synthesis function (TTS), you must specify the `speaker_voice` argument.")
        
        if not await self.is_ready():
            log.info("AsyncSileroTTS: Движок не готов. Пожалуйста, инициализируйте.")
            return False
        if not self._model: # Дополнительная проверка
            log.info("AsyncSileroTTS: Модель отсутствует.")
            return False


        try:
            print(f"AsyncSileroTTS: Синтез речи для: '{text}' голосом '{voice}'...")
            
            # Блокирующая операция TTS
            def _apply_tts_sync() -> torch.Tensor:
                if self._model is None:
                    raise RuntimeError("Модель TTS не инициализирована.")
                return self._model.apply_tts(
                    text=text,
                    speaker=voice,
                    sample_rate=self.sample_rate,
                    put_accent=True,
                    put_yo=True
                )
            
            # audio_tensor = await asyncio.get_event_loop().run_in_executor(None, _apply_tts_sync)
            if hasattr(asyncio, 'to_thread'):
                # Если есть to_thread, используем его для асинхронного вызова
                audio_tensor = await asyncio.to_thread(_apply_tts_sync)
            else:
                loop = asyncio.get_running_loop()
                audio_tensor = await loop.run_in_executor(None, _apply_tts_sync)
            audio_numpy = audio_tensor.cpu().numpy()

            print("AsyncSileroTTS: Воспроизведение аудио...")
            
            # sounddevice.play/wait блокирующие. Для asyncio их тоже нужно в executor.
            # Либо использовать асинхронную библиотеку для аудио, если есть.
            def _play_audio_sync():
                sd.play(audio_numpy, samplerate=self.sample_rate)
                sd.wait()
            
            if hasattr(asyncio, 'to_thread'):
                # Если есть to_thread, используем его для асинхронного вызова
                await asyncio.to_thread(_play_audio_sync)
            else:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _play_audio_sync)
            # await self._loop.run_in_executor(None, _play_audio_sync)
            
            print("AsyncSileroTTS: Воспроизведение завершено.")
            return True
        except Exception as e:
            print(f"AsyncSileroTTS: Ошибка при синтезе или воспроизведении: {e}")
            return False

    async def is_ready(self) -> bool:
        return self._is_initialized

    async def destroy(self) -> None:
        print("AsyncSileroTTS: Завершение работы...")
        self._model = None
        self._is_initialized = False
        # Здесь можно добавить освобождение других ресурсов, если они есть

if __name__ == '__main__':
    
    async_tts:AsyncSileroTTS
    
    phrases:Dict[str, List[tuple[str, str]]] = {
        "ru": [
            ("Привет из асинхронного мира!", "kseniya"),
            ("Кожанный мешок, я - робот В+ертер, слушаю тебя.", "aidar")
        ],
        "uz": [
            # ("Ish ishtaha ochar, dangasa ishdan qochar.-", "dilnavoz"),
            # ("Aql yoshda emas, boshda.-","dilnavoz"),
            # ("Bosh omon bo'lsa, do'ppi topiladi.-", "dilnavoz"),
            ("""
    Ne-ne allomalar sening sha’ningga,
    Go‘zal baytlar bitgan, fikrlar aytgan.
    Men ham bir farzanding, angladim, beshak,
    Sendan boshlanadi aslida Vatan!
    Asrlar bag‘rida mardona tilim,
    Sevib-ardoqlaymiz, ey, ona tilim!
""", "dilnavoz")
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
        print("Запуск асинхронной инициализации TTS...")
        # Запускаем инициализацию b ждем ее здесь,
        # если другие части приложения могут работать параллельно.
        init_started = await asilero_tts.load_and_init_model()
        if not init_started: # Это проверит только запуск задачи, а не готовность модели
            print("Failed to start TTS initialization task.")
            raise Exception("Failed to start TTS initialization task.")
            # return # Или другая обработка

        print("Инициализация TTS запущена. Продолжение работы основной программы...")
        
        # Эмулируем другую работу приложения
        # for i in range(5):
        #     print(f"Основное приложение работает... ({i+1}/5)")
        #     await asyncio.sleep(0.5) # Неблокирующая пауза

        # Теперь пытаемся использовать TTS
        # synthesize_speech_async сама дождется завершения инициализации, если нужно.
        for phrase_voice_tuple in phrases[test_language]:
            phrase: str = phrase_voice_tuple[0]
            voice: str = phrase_voice_tuple[1]
            await asilero_tts.speak(phrase, voice=voice)
            await asyncio.sleep(1)
        
        # await asilero_tts.speak("Привет из асинхронного мира!", speaker_voice='kseniya')
        # await asyncio.sleep(1)
        # await asilero_tts.speak("Я - робот В+ертер. Слушаю вас, кожанные мешки.", speaker_voice='aidar')
    
    try:
        asyncio.run(main_async(async_tts))
    except KeyboardInterrupt:
        log.warning("\nПрограмма прервана пользователем.")
    finally:
        # Здесь можно добавить корректное закрытие ресурсов, если необходимо
        # Например, дождаться завершения _is_initialized, если оно еще работает
        # и мы хотим чистого выхода.
        if not async_tts._is_initialized:
            log.info("Ожидание завершения инициализации TTS перед выходом...")