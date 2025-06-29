from typing import Callable, Dict, Any, List, Optional

# Определяем тип для наших функций-обработчиков.
# Они не принимают аргументов (пока) и могут возвращать что угодно (или ничего - None).
CommandHandler = Callable[[], Any] # или Callable[[], None] если они ничего не возвращают

# --- 1. Определяем твои функции-обработчики ---
def handle_time_command() -> None:
    print("Функция: Показать время")
    # Здесь будет логика получения и озвучивания времени

def handle_date_command() -> None:
    print("Функция: Показать дату")
    # Здесь будет логика получения и озвучивания даты

def handle_open_browser_command() -> None:
    print("Функция: Открыть браузер")
    # Здесь будет логика открытия браузера

def handle_open_terminal_command() -> None:
    print("Функция: Открыть терминал")
    # Здесь будет логика открытия терминала

def handle_exit_command() -> None:
    print("Функция: Завершить работу")
    # Здесь будет логика завершения программы
    exit()

# --- 2. Создаем словарь-маршрутизатор команд ---
# Ключ - это фраза-команда (или ее основная часть).
# Значение - это ссылка на функцию, которую нужно вызвать.
COMMAND_MAP: Dict[str, CommandHandler] = {
    "время": handle_time_command,
    "дата": handle_date_command,
    "открой браузер": handle_open_browser_command,
    "открой терминал": handle_open_terminal_command,
    "пока": handle_exit_command,
    "стоп": handle_exit_command, # Можно иметь несколько команд для одной функции
}

# --- 3. Функция для обработки распознанной команды ---
def process_command(recognized_text: str, command_mapping: Dict[str, CommandHandler]) -> None:
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

# --- Пример использования в твоем основном цикле ---
# Предположим, у тебя есть переменная `is_activated` и `recognized_text_from_stt`
# ... (код активации и получения recognized_text_from_stt) ...
# if is_activated:
#     if recognized_text_from_stt: # если что-то распознано
#         process_command(recognized_text_from_stt, COMMAND_MAP)
#         is_activated = False # Сбросить активацию после команды
#         # ... прочие действия ...
# ...

# --- Демонстрация работы process_command ---
if __name__ == "__main__":
    test_commands = [
        "время",
        "Зумрад, дата", # Этот вариант потребует доработки в process_command или предварительной очистки
        "открой браузер",
        "Зумрад открой терминал пожалуйста",
        "скажи что-нибудь",
        "пока",
    ]

    print("--- Тестирование с точным совпадением (упрощенный process_command) ---")
    # Упрощенная версия process_command для демонстрации точного совпадения
    def process_command_simple(recognized_text: str, command_mapping: Dict[str, CommandHandler]) -> None:
        cmd = recognized_text.lower().strip()
        if cmd in command_mapping:
            print(f"Выполнение (точное совпадение) для: '{cmd}'")
            command_mapping[cmd]()
        else:
            print(f"Неизвестная команда (точное совпадение): '{cmd}'")

    for test_cmd in test_commands:
        # Для простоты пока предположим, что ключевое слово "Зумрад" уже отфильтровано
        # и `test_cmd` это уже часть команды
        cleaned_command = test_cmd.replace("зумрад", "").replace("пожалуйста", "").strip()
        # process_command_simple(cleaned_command, COMMAND_MAP) # Простой вариант
        process_command(cleaned_command, COMMAND_MAP) # Более сложный вариант с поиском подстроки