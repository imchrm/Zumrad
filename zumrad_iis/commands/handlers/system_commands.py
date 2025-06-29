from datetime import datetime
import logging

log = logging.getLogger(__name__)

def what_time_is_it():
    """
    Выводит текущее время в формате ЧЧ:ММ:СС.
    """
    current_time = datetime.now().strftime("%H:%M:%S")
    log.info(f"Текущее время: {current_time}")
    
    def launch_videoplayer(self):
        """
        Запускает видеоплеер из возможных.
        """
        # Попробуем несколько распространенных видеоплееров
        self._launch_external_process([
                "celluloid",           # Celluloid (ранее GNOME MPV)
                "vlc",                 # VLC Media Player
                "mpv",                 # MPV Media Player
                "smplayer",            # SMPlayer
                "totem",               # Totem (GNOME Video Player)
                "mplayer"              # MPlayer
            ])