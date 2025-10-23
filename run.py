# run.py
"""
# run.py
"""
# Может быть помещено в другой модуль, где вы импортируете AsyncSileroTTS
from typing import Dict, List
import logging

from zumrad_iis import config

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

import asyncio
from test.tts_implemintations.test_asilero_tts import AsyncSileroTTS
from zumrad_iis.main import VoiceAssistant

log: logging.Logger = logging.getLogger(__name__)

async def main() -> None:
    # Настройка логирования должна быть здесь, если run.py не используется как точка входа
    # или если вы хотите переопределить настройки из run.py
    # logging.basicConfig(
    #     level=logging.DEBUG, # или config.LOG_LEVEL
    #     format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    # )
    config.load_and_apply_config()
    assistant = VoiceAssistant(config)
    await assistant.run()

if __name__ == '__main__':
    # asyncio.get_event_loop().run_in_executor(None, interactive_run)
    asyncio.run(main())