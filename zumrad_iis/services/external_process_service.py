from typing import List
import subprocess
import platform

process = None  # Переменная для хранения процесса терминала

class ExternalProcessService:
    
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
        
    def _launch_external_process(self, names: List[str]):
        """
        Запускаем процесс первый сработавший из списка `names`.
        """
        current_os = platform.system()
        command = None

        if current_os == "Linux":
            # Перебираем разные варианты команд для запуска процесса
            for cmd in names:
                try:
                    # Используем Popen для запуска в фоновом режиме, чтобы скрипт не ждал закрытия процесса
                    global process
                    process = subprocess.Popen([cmd])
                    
                    print(f"Попытка открыть процесс с помощью команды: {cmd}")
                    command = cmd
                    break # Выходим из цикла, если команда успешно запущена
                except FileNotFoundError:
                    print(f"Команда '{cmd}' не найдена, пробуем следующую...")
                except Exception as e:
                    print(f"Ошибка при попытке открыть процесс с помощью '{cmd}': {e}")
                    # Не выходим из цикла, пробуем следующую команду
            
            if command:
                print(f"Процесс успешно запущен с помощью '{command}'.")
            else:
                print("Не удалось найти и запустить ни один из процессов представленных в `names`.")
                print("Пожалуйста, убедитесь, что у вас установлен запускаемый процесс и он доступен в PATH.")