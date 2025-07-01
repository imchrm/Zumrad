import asyncio
from typing import Callable, Dict, Any, List, Optional
import logging as log
import threading
from datetime import datetime
import random
import subprocess
import platform
import json
import queue # Для потокобезопасной очереди
import vosk
import sounddevice as sd
from pydub import AudioSegment
from pydub.playback import play

log.basicConfig(
    level=log.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Определяем тип для наших функций-обработчиков.
# Они не принимают аргументов (пока) и могут возвращать что угодно (или ничего - None).
CommandHandler = Callable[[], Any] # или Callable[[], None] если они ничего не возвращают

# Настройки
# STT_MODEL_NAME = "uz-UZ"  # Локаль для распознавания речи
STT_MODEL_NAME = "ru-RU"  # Имя папки модели для распознавания речи
STT_MODEL_PATH = "stt_models/"  # Путь к папке с распакованной моделью
DEVICE_ID = None      # ID устройства ввода (микрофона), None - устройство по умолчанию
SAMPLERATE = 16000    # Частота дискретизации, с которой обучена модель Vosk
CHANNELS = 1          # Моно
BLOCKSIZE = 8000      # Размер блока данных (в семплах) для обработки
PHRASES_TO_EXIT = ["завершить работу", "завершить сеанс", "выход", "выйди", "закрыть программу",
                "заверши работу", "заверши сеанс", "завершить зум рады", "завершит работу", "завершит сеанс", "закрой программу",]

process = None  # Переменная для хранения процесса терминала

IS_ACTIVATED = False

# Ключевое слово и звук активации
# KEYWORD = "zumrad"  # В нижнем регистре
KEYWORD = "изумруд"  # В нижнем регистре
ACTIVATION_SOUND_PATH = "assets/sound/bdrim.mp3" # Путь к звуковому файлу (или mp3)
COMMAND_SOUND_PATH = "assets/sound/snap.mp3" # Путь к звуковому файлу (или mp3)



def check_is_exit_phrase(text) -> bool:
    """Проверяет, не является ли сказанное одной из фраз для выхода."""
    is_exit = False
    for phrase in PHRASES_TO_EXIT:
        if phrase in text.lower():
            # print(f"Вы сказали '{phrase}', завершение работы...")
            is_exit = True
            break
    return is_exit

async def play_zumrad_sound(sound_path: str):
    """Воспроизводит звук активации в основном потоке."""
    try:
        # Загружаем аудиофайл с помощью pydub
        sound = AudioSegment.from_file(sound_path)
        # Воспроизводим его в отдельном потоке, чтобы не блокировать asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, play, sound)
    except Exception as e:
        log.error(f"Не удалось воспроизвести звук {sound_path} с помощью pydub: {e}")

def clear_audio_queue(audio_queue):
    """Очищает очередь от всех накопившихся аудиоданных."""
    # print("Очистка аудио очереди...") # Для отладки
    while not audio_queue.empty():
        try:
            audio_queue.get_nowait() # Извлекаем без ожидания
        except queue.Empty:
            # Эта ситуация не должна возникнуть в while not audio_queue.empty(),
            # но на всякий случай.
            break
    # print("Аудио очередь очищена.") # Для отладки

# C O M M A N D S
# Функции для обработки команд

def run_terminal():
    """
    Запускает терминал из возможных.
    """
    # Попробуем несколько распространенных команд для терминалов
    # x-terminal-emulator обычно является ссылкой на терминал по умолчанию
    run_external_process([
            "celluloid",
            "x-terminal-emulator",
            "gnome-terminal",      # Для GNOME, Cinnamon (Linux Mint)
            "mate-terminal",       # Для MATE
            "xfce4-terminal",      # Для XFCE
            "konsole",             # Для KDE
            "lxterminal",          # Для LXDE
            "terminator",          # Популярный альтернативный терминал
            "tilix",               # Еще один популярный терминал
            "xterm"                # Стандартный X11 терминал (запасной вариант)
        ])
def run_videoplayer():
    """
    Запускает видеоплеер из возможных.
    """
    # Попробуем несколько распространенных видеоплееров
    run_external_process([
            "celluloid",           # Celluloid (ранее GNOME MPV)
            "vlc",                 # VLC Media Player
            "mpv",                 # MPV Media Player
            "smplayer",            # SMPlayer
            "totem",               # Totem (GNOME Video Player)
            "mplayer"              # MPlayer
        ])
def run_external_process(names: List[str]):
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

def what_time():
    """
    Выводит текущее время в формате ЧЧ:ММ:СС.
    """
    current_time = datetime.now().strftime("%H:%M:%S")
    print(f"Текущее время: {current_time}")

def tell_joke():
    """
    Рассказывает случайный анекдот.
    """
    jokes = [
        "Почему программисты не любят природу? Потому что там слишком много багов!",
        "Какой язык программирования самый оптимистичный? Python, потому что он всегда в хорошей форме!",
        "Почему JavaScript не может найти себе пару? Потому что у него слишком много асинхронных отношений!",
        "Какой язык программирования самый романтичный? Ruby, потому что он всегда в поиске идеального объекта!"
    ]
    joke = random.choice(jokes)
    print(f"Анекдот: {joke}")

def process_command(recognized_text: str, command_mapping: Dict[str, CommandHandler]) -> bool:
    """
    Ищет команду в словаре и выполняет соответствующую функцию.
    """
    command_to_execute: Optional[CommandHandler] = None
    
    # Простой поиск точного совпадения (можно усложнить, если нужно)
    # Приводим к нижнему регистру для унификации
    processed_text = recognized_text.lower().strip()

    if processed_text in command_mapping:
        command_to_execute = command_mapping[processed_text]
    else:
        # Более сложный поиск: если команда является частью фразы
        # Например, "Зумрад, открой браузер быстро" -> сработает на "открой браузер"
        # Это более продвинутый вариант, для начала можно обойтись точным совпадением.
        for command_phrase in command_mapping.keys():
            if command_phrase in processed_text:
                command_to_execute = command_mapping[command_phrase]
                print(f"Найдена подстрока-команда: '{command_phrase}' в '{processed_text}'")
                break 
                # Важно! break, чтобы не выполнить несколько команд, если одна является подстрокой другой

    if command_to_execute:
        print(f"Выполнение команды для: '{processed_text}'")
        command_to_execute() # Вызываем найденную функцию
    else:
        print(f"Неизвестная команда: '{recognized_text}'")
        return False # Команда не найдена, возвращаем False
    return True # Команда найдена и выполнена, возвращаем True

def _wait_and_cleanup_terminal(proc: subprocess.Popen):
    pid = proc.pid # Сохраняем PID на случай, если proc станет None раньше
    print(f"Ожидание завершения терминала (PID: {pid}) в отдельном потоке...")
    try:
        proc.terminate()
        # proc.send_signal(signal.SIGTERM) # Отправляем сигнал SIGTERM
        try:
            proc.wait(timeout=2)
            print(f"Терминал (PID: {pid}) должен был завершиться (SIGTERM).")
        except subprocess.TimeoutExpired:
            print(f"Терминал (PID: {pid}) не завершился после SIGTERM, попытка SIGKILL...")
            proc.kill()
            proc.wait(timeout=1) # Короткое ожидание после SIGKILL
            print(f"Терминал (PID: {pid}) должен был завершиться (SIGKILL).")
        
        status = proc.poll()
        print(f"Статус процесса терминала (PID: {pid}) после попытки закрытия: {status}")

    except ProcessLookupError:
        print(f"Процесс терминала (PID: {pid}) уже не существует к моменту ожидания.")
    except Exception as e:
        print(f"Ошибка в потоке ожидания закрытия терминала (PID: {pid}): {e}")
    
    # Важно: если `terminal` все еще ссылается на этот же процесс, обнуляем его
    global process
    if process is proc: # Проверяем, что это тот же самый объект Popen
        process = None
        print(f"Глобальная ссылка на терминал (PID: {pid}) очищена из потока.")

def terminate_process_threaded():
    global process
    if process and process.poll() is None:
        print(f"Запуск потока для закрытия терминала (PID: {process.pid})...")
        # Сохраняем текущий объект Popen для передачи в поток,
        # чтобы избежать гонки состояний, если terminal будет изменен до запуска потока.
        proc_to_terminate = process 
        
        # Важно! Мы можем сразу же обнулить `terminal` здесь в основном потоке,
        # чтобы система считала, что терминала больше нет,
        # а фоновый поток уже займется его фактическим закрытием.
        # Но это если не нужна проверка `terminal is proc` в потоке.
        # Для большей безопасности, пока оставим обнуление в потоке.
        # terminal = None 
        
        thread = threading.Thread(target=_wait_and_cleanup_terminal, args=(proc_to_terminate,))
        thread.daemon = True # Поток завершится, если основной процесс завершится
        thread.start()
    elif process and process.poll() is not None:
        print("Терминал был запущен, но уже завершился ранее.")
        process = None
    else:
        print("Терминал не был запущен или ссылка на него уже очищена.")


# Ключ - это фраза-команда (или ее основная часть).
# Значение - это ссылка на функцию, которую нужно вызвать.
COMMAND_MAP: Dict[str, CommandHandler] = {
    "запусти видеоплеер": run_videoplayer,
    "завершить видеоплеер": terminate_process_threaded,
    "заверши видеоплеер": terminate_process_threaded,
    "сколько времени": what_time,
    "расскажи анекдот": tell_joke
}

# Очередь для передачи аудиоданных из callback'а в основной поток
q = queue.Queue()

def callback(indata, frames, time, status):
    """Это вызывается для каждого блока аудио из потока."""
    if status:
        print(status, flush=True)
    q.put(bytes(indata))

async def main_loop():
    
    # asilero = ASileroTTS(language="uz", model_id="v4_uz")
    # await asilero.initialize_tts_model()

    try:
        global IS_ACTIVATED, STT_MODEL_PATH, DEVICE_ID, SAMPLERATE, CHANNELS, BLOCKSIZE
        
        STT_MODEL_PATH = STT_MODEL_PATH + STT_MODEL_NAME
        
        # Проверка наличия модели
        if not vosk.Model(STT_MODEL_PATH):
            print(f"Модель не найдена по пути: {STT_MODEL_PATH}")
            print("Пожалуйста, скачайте модель с https://alphacephei.com/vosk/models")
            print("и распакуйте ее в папку соответствующей 'model' в корне проекта.")
            exit(1)

        # Загрузка модели
        model = vosk.Model(STT_MODEL_PATH)
        recognizer = vosk.KaldiRecognizer(model, SAMPLERATE)
        recognizer.SetWords(True) # Чтобы видеть распознанные слова, а не только полный текст
        
        devices = sd.query_devices()
        
        print(f"Доступные устройства для захвата голоса:")
        if devices:
            for i, device in enumerate(devices):
                name = device.get('name', '') if isinstance(device, dict) else str(device)
                print(f"{i}: {name}")
        if DEVICE_ID is not None and DEVICE_ID >= len(devices):
            print(f"Устройство с ID {DEVICE_ID} не найдено.")
            exit(1)
        current_device = sd.query_devices(DEVICE_ID, 'input')
        if current_device:
            name_current_device = current_device.get('name', '') if isinstance(current_device, dict) else str(current_device)
            print(f"Используется устройство: {name_current_device if DEVICE_ID else 'Устройство по умолчанию'}")
        print("Говорите. Для остановки нажмите Ctrl+C")

        # Начинаем запись с микрофона
        # with sd.RawInputStream(callback=q_callback, channels=1, samplerate=samplerate, device=device_m, dtype='int16')
        with sd.RawInputStream(samplerate=SAMPLERATE, blocksize=BLOCKSIZE,
                            device=DEVICE_ID, dtype='int16',
                            channels=CHANNELS, callback=callback):

            while True:
                data = q.get() # Получаем данные из очереди
                if recognizer.AcceptWaveform(data):
                    result_json = recognizer.Result()
                    result_dict = json.loads(result_json)
                    # print("Полный результат:", result_dict)
                    recognized_text: str = result_dict.get("text", "")
                    
                    if not recognized_text: # Пропускаем пустые результаты (часто из-за пауз)
                        continue
                    
                    if check_is_exit_phrase(recognized_text):
                        print("Завершение работы...")
                        exit(1)
                    
                    print(">>:", recognized_text)
                    
                    if IS_ACTIVATED:
                        if recognized_text.lower().startswith(KEYWORD):
                            print("Система уже активирована. Пожалуйста, произнесите вашу команду.")
                            # Можно решить, нужно ли здесь повторное подтверждение или очистка
                            # play_activation_sound()
                            # clear_audio_queue(q)
                            # recognizer.Reset()
                        else:
                            # >>> В БУДУЩЕМ ЗДЕСЬ БУДЕТ ОБРАБОТКА КОМАНДЫ <<<
                            is_executed = process_command(recognized_text, COMMAND_MAP)
                            if is_executed:
                                IS_ACTIVATED = False # Сбрасываем активацию после получения команды
                                await play_zumrad_sound(COMMAND_SOUND_PATH)
                            
                            print(f"Команда {'выполнена!'if is_executed else 'не распознана!'}")
                            
                                
                            # for com in COMMANDS:
                            #     if com.startswith(recognized_text):
                            #         IS_ACTIVATED = False # Сбрасываем активацию после получения команды
                            #         print(f"Получена команда: {recognized_text}")
                            #         play_zumrad_sound(COMMAND_SOUND_PATH)
                            #         # recognizer.Reset() # Сброс здесь необязателен, т.к. команда получена.
                            #         # Он будет сделан перед следующей активацией.
                            #         print(f"\nКоманда '{recognized_text}' принята.")
                            #         print(f"Скажите '{KEYWORD.capitalize()}' для следующей активации.")
                    
                    else: # is_activated == False, система ждет ключевое слово
                        if recognized_text.startswith(KEYWORD):
                            
                            
                            recognized_text = recognized_text[len(KEYWORD):].strip() # Убираем ключевое слово из начала текста
                            
                            if not recognized_text: # Если после ключевого слова ничего не сказано
                                # 1. Если ключевое слово распознано, но нет команды, активируем систему.
                                IS_ACTIVATED = True
                                await play_zumrad_sound(ACTIVATION_SOUND_PATH)
                                # 3. Очищаем аудио очередь от данных, накопившихся во время
                                #    распознавания ключевого слова и воспроизведения звука.
                                clear_audio_queue(q)
                                # 4. Сбрасываем состояние распознавателя, чтобы он был готов
                                #    к приему новой команды "с чистого листа".
                                recognizer.Reset()
                                print(f"Ключевое слово '{KEYWORD}' распознано!")
                                print(f"Жду вашу команду...")
                            else:
                                # Распознано ключевое слово, но сразу за ним идет текст команды.
                                # Можно сразу обработать команду, если она есть.
                                print(f"Ключевое слово '{KEYWORD}' распознано с командой: '{recognized_text}'")
                                is_executed = process_command(recognized_text, COMMAND_MAP)
                                if is_executed:
                                    IS_ACTIVATED = False
                                    await play_zumrad_sound(COMMAND_SOUND_PATH)
                        # else:
                            # Распознан текст, но это не ключевое слово, и система не активирована.
                            # Можно логировать или игнорировать.
                            # print(f"Посторонний шум/речь: '{recognized_text}'")
                            # Продолжаем слушать
                            
                        
                    
                # else:
                #     partial_result_json = recognizer.PartialResult()
                #     partial_dict = json.loads(partial_result_json)
                #     if partial_dict.get("partial", ""):
                #         print("Промежуточный результат:", partial_dict["partial"])


    except KeyboardInterrupt:
        print("\nЗавершение работы...")
    except (sd.PortAudioError, RuntimeError, OSError) as e:
        print(f"Произошла ошибка: {e}")
        if "PortAudio library not found" in str(e) or "No Default Input Device Available" in str(e):
            print("Пожалуйста, убедитесь, что PortAudio установлен (sudo apt install portaudio19-dev) и микрофон подключен и настроен.")
            print("Список доступных устройств:")
            print(sd.query_devices())
        if "playsound" in str(e).lower() or "gstreamer" in str(e).lower():
            print("Проблема с воспроизведением звука. Убедитесь, что установлены 'playsound', 'PyGObject' и системные компоненты GStreamer (см. инструкцию).")


if __name__ == '__main__':
    asyncio.run(main_loop())