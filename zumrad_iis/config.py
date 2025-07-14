# config.py
from unittest.mock import DEFAULT
import yaml
import os
import logging
from typing import List, Optional, Any, Dict

log = logging.getLogger(__name__) # Используем логгер модуля

# Пояснение почему НЕ нужно инкапсулировать переменные в класс:
# В Python каждый файл `*.py` (модуль) 
# сам по себе является объектом и предоставляет пространство имен.
# Подход с модулем часто считается более простым и прямолинейным для глобальных конфигураций. 
# Нет необходимости в дополнительной структуре класса, 
# если он не несет дополнительной логики (методов, инкапсуляции состояния экземпляров и т.д.). 

# --- Значения по умолчанию ---
# Эти значения будут использоваться, если config.yaml не найден
# или если в нем отсутствуют соответствующие ключи.

# STT Настройки
DEFAULT_STT_MODEL_NAME: str = "ru-RU"
DEFAULT_STT_MODEL_PATH_BASE: str = "stt_models/"
DEFAULT_STT_SAMPLERATE: int = 16000
DEFAULT_STT_CHANNELS: int = 1
DEFAULT_STT_BLOCKSIZE: int = 8000
DEFAULT_STT_DEVICE_ID: Optional[int] = None # None для устройства по умолчанию

# Настройки активации
DEFAULT_STT_KEYWORD: str = "изумруд"
DEFAULT_ACTIVATION_SOUND_PATH: str = "assets/sound/bdrim.wav"
DEFAULT_COMMAND_SOUND_PATH: str = "assets/sound/snap.wav"

# TTS Настройки
DEFAULT_TTS_LANGUAGE: str = "ru"
DEFAULT_TTS_MODEL_ID: str = "v3_1_ru"
DEFAULT_TTS_VOICE: str = "kseniya"  # Голос по умолчанию, если не указан
DEFAULT_TTS_SAMPLERATE: int = 48000
DEFAULT_TTS_DEVICE: str = "cpu"

# Общие настройки
DEFAULT_PHRASES_TO_EXIT: List[str] = [
    "завершить работу", "завершить сеанс", "выход", "выйди", "закрыть программу",
    "заверши работу", "заверши сеанс", "завершить зум рады", "завершит работу", "завершит сеанс", "закрой программу",
]

# --- Загрузка конфигурации ---
# Путь к файлу конфигурации (относительно корня проекта или места запуска a_main.py)
CONFIG_FILE_PATH: str = "config.yaml"

# Инициализация переменных конфигурации значениями по умолчанию
STT_MODEL_NAME: str = DEFAULT_STT_MODEL_NAME
STT_MODEL_PATH_BASE: str = DEFAULT_STT_MODEL_PATH_BASE
STT_SAMPLERATE: int = DEFAULT_STT_SAMPLERATE
STT_CHANNELS: int = DEFAULT_STT_CHANNELS
STT_BLOCKSIZE: int = DEFAULT_STT_BLOCKSIZE
STT_DEVICE_ID: Optional[int] = DEFAULT_STT_DEVICE_ID
STT_KEYWORD: str = DEFAULT_STT_KEYWORD
ACTIVATION_SOUND_PATH: str = DEFAULT_ACTIVATION_SOUND_PATH
COMMAND_SOUND_PATH: str = DEFAULT_COMMAND_SOUND_PATH
TTS_SAMPLERATE: int = DEFAULT_TTS_SAMPLERATE
TTS_LANGUAGE: str = DEFAULT_TTS_LANGUAGE
TTS_VOICE: str = DEFAULT_TTS_VOICE  # Голос по умолчанию, если не указан
TTS_MODEL_ID: str = DEFAULT_TTS_MODEL_ID
TTS_DEVICE: str = DEFAULT_TTS_DEVICE

# Список фраз для выхода из программы
PHRASES_TO_EXIT: List[str] = list(DEFAULT_PHRASES_TO_EXIT) # Копируем список, чтобы избежать изменения оригинала

# Производная конфигурация (обновляется после загрузки основных)
STT_MODEL_PATH: str = os.path.join(STT_MODEL_PATH_BASE, STT_MODEL_NAME)

def _load_and_apply_config():
    """Загружает конфигурацию из YAML и применяет ее, переопределяя значения по умолчанию."""
    global STT_MODEL_NAME, STT_MODEL_PATH_BASE, STT_SAMPLERATE, STT_CHANNELS, STT_BLOCKSIZE, STT_DEVICE_ID
    global TTS_LANGUAGE, TTS_MODEL_ID, TTS_VOICE, TTS_SAMPLERATE, TTS_DEVICE
    global STT_KEYWORD, ACTIVATION_SOUND_PATH, COMMAND_SOUND_PATH, PHRASES_TO_EXIT
    global STT_MODEL_PATH # Для обновления производной конфигурации

    yaml_config: Dict[str, Any] = {}
    if not os.path.exists(CONFIG_FILE_PATH):
        log.warning(f"Файл конфигурации '{CONFIG_FILE_PATH}' не найден. Используются значения по умолчанию.")
    else:
        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                loaded_yaml = yaml.safe_load(f)
                if loaded_yaml: # Проверка, что файл не пустой
                    yaml_config = loaded_yaml
                    log.info(f"Конфигурация успешно загружена из '{CONFIG_FILE_PATH}'.")
                else:
                    log.warning(f"Файл конфигурации '{CONFIG_FILE_PATH}' пуст. Используются значения по умолчанию.")
        except yaml.YAMLError as e:
            log.error(f"Ошибка парсинга YAML файла '{CONFIG_FILE_PATH}': {e}. Используются значения по умолчанию.")
        except Exception as e:
            log.error(f"Не удалось прочитать файл конфигурации '{CONFIG_FILE_PATH}': {e}. Используются значения по умолчанию.")

    # Применяем загруженные значения, если они есть в YAML
    # STT Настройки
    stt_settings = yaml_config.get("stt", {})
    STT_MODEL_NAME = stt_settings.get("model_name", DEFAULT_STT_MODEL_NAME)
    STT_MODEL_PATH_BASE = stt_settings.get("model_path_base", DEFAULT_STT_MODEL_PATH_BASE)
    STT_SAMPLERATE = stt_settings.get("samplerate", DEFAULT_STT_SAMPLERATE)
    STT_CHANNELS = stt_settings.get("channels", DEFAULT_STT_CHANNELS)
    STT_BLOCKSIZE = stt_settings.get("blocksize", DEFAULT_STT_BLOCKSIZE)
    STT_DEVICE_ID = stt_settings.get("device_id", DEFAULT_STT_DEVICE_ID) # YAML null станет None

    # Настройки активации
    activation_settings = yaml_config.get("activation", {})
    STT_KEYWORD = activation_settings.get("keyword", DEFAULT_STT_KEYWORD)
    ACTIVATION_SOUND_PATH = activation_settings.get("activation_sound_path", DEFAULT_ACTIVATION_SOUND_PATH)
    COMMAND_SOUND_PATH = activation_settings.get("command_sound_path", DEFAULT_COMMAND_SOUND_PATH)

    # TTS Настройки
    tts_settings = yaml_config.get("tts", {})
    TTS_LANGUAGE = tts_settings.get("language", DEFAULT_TTS_LANGUAGE)
    TTS_MODEL_ID = tts_settings.get("model_id", DEFAULT_TTS_MODEL_ID)
    TTS_VOICE = tts_settings.get("voice", DEFAULT_TTS_VOICE)
    TTS_SAMPLERATE = tts_settings.get("samplerate", DEFAULT_TTS_SAMPLERATE)
    TTS_DEVICE = tts_settings.get("device", DEFAULT_TTS_DEVICE)
    
    # Общие настройки
    general_settings = yaml_config.get("general", {})
    PHRASES_TO_EXIT = general_settings.get("phrases_to_exit", list(DEFAULT_PHRASES_TO_EXIT))

    # Обновляем производные пути
    STT_MODEL_PATH = os.path.join(STT_MODEL_PATH_BASE, STT_MODEL_NAME)
    log.debug(f"Итоговый путь к STT модели: {STT_MODEL_PATH}")

# Загружаем конфигурацию при импорте модуля
_load_and_apply_config()

# (Опционально) Функция для вывода текущей конфигурации для отладки
def print_active_config():
    log.info("--- Текущая активная конфигурация ---")
    log.info(f"  STT Model Name: {STT_MODEL_NAME}")
    log.info(f"  STT Model Path Base: {STT_MODEL_PATH_BASE}")
    log.info(f"  STT Model Full Path: {STT_MODEL_PATH}")
    log.info(f"  Sample Rate: {STT_SAMPLERATE}")
    log.info(f"  Channels: {STT_CHANNELS}")
    log.info(f"  Blocksize: {STT_BLOCKSIZE}")
    log.info(f"  Device ID: {STT_DEVICE_ID}")
    log.info(f"  Keyword: {STT_KEYWORD}")
    log.info(f"  Activation Sound: {ACTIVATION_SOUND_PATH}")
    log.info(f"  Command Sound: {COMMAND_SOUND_PATH}")
    log.info(f"  TTS Language: {TTS_LANGUAGE}")
    log.info(f"  TTS Model ID: {TTS_MODEL_ID}")
    log.info(f"  TTS Voice: {TTS_VOICE}")
    log.info(f"  TTS Sample Rate: {TTS_SAMPLERATE}")
    log.info(f"  TTS Device: {TTS_DEVICE}")
    log.info(f"  Phrases to Exit: {PHRASES_TO_EXIT}")
    log.info("------------------------------------")

if __name__ == '__main__':
    # Для тестирования самого модуля config.py
    print_active_config()

    # Пример создания config.yaml, если его нет, для тестирования
    if not os.path.exists(CONFIG_FILE_PATH):
        dummy_yaml_content = """
stt:
  model_name: "vosk-model-small-ru-0.22" # Пример другого имени
  # samplerate: 8000 # Пример переопределения
  device_id: 0 # Пример указания конкретного устройства

activation:
  keyword: "ассистент"

general:
  phrases_to_exit:
    - "стоп"
    - "хватит"
"""
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(dummy_yaml_content)
        log.info(f"Создан тестовый '{CONFIG_FILE_PATH}'. Перезапустите для проверки загрузки из него.")
