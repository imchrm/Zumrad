import asyncio
import logging
from typing import Dict, List
from zumrad_iis.tts_implementations.async_silero_tts import AsyncSileroTTS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

log = logging.getLogger(__name__)

if __name__ == '__main__':
    
    # source .venv/bin/activate
    # python3 test/tts_implemintations/test_async_tts.py

    async_tts:AsyncSileroTTS
    
    phrases:Dict[str, List[tuple[str, str]]] = {
        "ru": [
            ("Привет из асинхронного мира!", "kseniya"),
            ("Я - робот В+ертер. Кожанный мешок, слушаю тебя.", "aidar")
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
    model_id = "v3_uz" # v4_uz | v3_uz
    if test_language == "uz":
        async_tts = AsyncSileroTTS(language="uz", model_id=model_id, sample_rate=48000)
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
            log.error("Failed to start TTS initialization task.")
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
        # Например, дождаться завершения model_initialization_task, если оно еще работает
        # и мы хотим чистого выхода.
        if async_tts._model_initialization_task and not async_tts._model_initialization_task.done():
            log.info("Ожидание завершения фоновой задачи инициализации TTS перед выходом...")
            # asyncio.run(model_initialization_task) # Не совсем корректно так вызывать run повторно
            # Лучше управлять жизненным циклом задач внутри основного `async def main`
            pass