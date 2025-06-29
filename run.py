# run.py
"""
# run.py
"""
# Может быть помещено в другой модуль, где вы импортируете AsyncSileroTTS
from typing import Dict, List
import logging
import asyncio
from zumrad_iis.tts_implementations.asilero_tts import AsyncSileroTTS
from zumrad_iis.main import VoiceAssistant

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__) 

async def interactive_run():
    async_tts: AsyncSileroTTS
    
    phrases: Dict[str, List[tuple[str, str]]] = {
        "ru": [
            ("Привет из асинхронного мира!", "kseniya"),
            ("Я - робот В+ертер. Кожанный мешок, слушаю тебя.", "aidar")
        ],
        "uz": [
            ("Ish ishtaha ochar, dangasa ishdan qochar.-", "dilnavoz"),
            ("Aql yoshda emas, boshda.-", "dilnavoz"),
            ("Bosh omon bo'lsa, do'ppi topiladi.-", "dilnavoz"),
        ]
    }
    test_language = "uz"
    
    if test_language == "uz":
        async_tts = AsyncSileroTTS(language="uz", model_id="v4_uz", sample_rate=48000)
    elif test_language == "ru":
        async_tts = AsyncSileroTTS(language="ru", model_id="v3_1_ru", sample_rate=48000)
    else:
        raise ValueError(f"Unsupported language: {test_language}")
    
    async def main_async(asilero_tts: AsyncSileroTTS):
        print("Запуск асинхронной инициализации TTS...")
        init_started = await asilero_tts.load_and_init_model()
        if not init_started:
            print("Failed to start TTS initialization task.")
            raise Exception("Initialization failed.")
        
        print("Инициализация TTS запущена. Основное приложение работает...")
        for i in range(5):
            print(f"Основное приложение работает... ({i+1}/5)")
            await asyncio.sleep(0.5)
        
        for phrase in phrases[test_language]:
            await asilero_tts.speak(phrase[0], voice=phrase[1])
            await asyncio.sleep(1)
    
    try:
        await main_async(async_tts)
    except KeyboardInterrupt:
        print("\nПрограмма прервана пользователем.")
    finally:
        if not async_tts.is_ready:
            print("Ожидание завершения инициализации TTS перед выходом...")

async def main():
    # Настройка логирования должна быть здесь, если run.py не используется как точка входа
    # или если вы хотите переопределить настройки из run.py
    logging.basicConfig(
        level=logging.INFO, # или config.LOG_LEVEL
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    assistant = VoiceAssistant()
    await assistant.run()

if __name__ == '__main__':
    # asyncio.get_event_loop().run_in_executor(None, interactive_run)
    asyncio.run(main())