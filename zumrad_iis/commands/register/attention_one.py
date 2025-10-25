import logging
from zumrad_iis.commands.command_processor import Command
from zumrad_iis.core.tts_interface import ITextToSpeech

log: logging.Logger = logging.getLogger(__name__) 

class SpeakCommand(Command):
    def __init__(self, tts_service: ITextToSpeech, text: str, voice: str | None = None) -> None:
        self.tts_service: ITextToSpeech = tts_service
        self.text: str = text
        self.voice: str | None = voice
        ...
    async def say(self, text: str, voice: str | None):
        if await self.tts_service.is_ready():
            # Голос по умолчанию можно брать из конфигурации, если не передан
            speaker_voice: str | None = voice
            await self.tts_service.speak(text, voice=speaker_voice)
        else:
            log.warning(f"Service TTS not ready. I can't speak: \n```{text}.```\n Check configuration of TTS service in config.yaml.")
            log.debug(f"ASSISTANT (fallback): {text}") # Запасной вариант вывода

class AttentionOneCommand(SpeakCommand):

    def __init__(self, tts_service: ITextToSpeech, text: str, voice: str | None = None) -> None:
        super().__init__(tts_service, text, voice)
        ...
    async def run(self, command_name: str | None) -> None:
        await self.say(self.text, self.voice)

    