
import logging
from pydub import AudioSegment
from pydub.playback import play
import asyncio
from tempfile import NamedTemporaryFile
import subprocess


log: logging.Logger = logging.getLogger(__name__) 

# TODO: Test this class 
class AudioPlayer(object):
    """
    A simple audio player class that uses ffplay to play audio segments.
    """
    PLAYER = "ffplay"

    @staticmethod
    def play_segment(seg: AudioSegment) -> None:
        """
        Plays an AudioSegment using ffplay.
        """
        with NamedTemporaryFile("w+b", suffix=".wav", delete=False) as f:
            temp_filename: str = f.name
            seg.export(temp_filename, format="wav")
        try:
            subprocess.call([AudioPlayer.PLAYER, "-nodisp", "-autoexit", "-hide_banner", temp_filename])
        except Exception as e:
            log.error(f"Error playing audio with ffplay: {e}")
        finally:
            import os
            os.remove(temp_filename)

class AudioFeedbackService:
    """
    Сервис для воспроизведения звуковых сигналов обратной связи.
    """
    def __init__(self, sound_path: str) -> None:
        self.sound_path: str = sound_path

    async def play_sound(self, sound_path: str):
        log.debug(f"Playing sound: {sound_path}")
        # Fix of `PermissionError: [Errno 13] Permission denied` issue when using pydub for playing temp audio files under Windows`
        # https://github.com/jiaaro/pydub/issues/209
        # This is changed method from pydub.playback 
        PLAYER = "ffplay"
        def _play_with_ffplay(seg: AudioSegment, player:str):
             
            with NamedTemporaryFile("w+b", suffix=".wav") as f:
                f.close() # close the file stream
                seg.export(f.name, format="wav")
                subprocess.call([player, "-nodisp", "-autoexit", "-hide_banner", f.name])
            
        try:
            # Load audio file by `pydub`
            sound = AudioSegment.from_file(sound_path)
            # Воспроизводим его в отдельном потоке, чтобы не блокировать asyncio
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _play_with_ffplay, sound, PLAYER)
        except Exception as e:
            log.error(f"Не удалось воспроизвести звук {sound_path} с помощью {PLAYER}: {e}")
