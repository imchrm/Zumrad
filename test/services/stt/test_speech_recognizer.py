
import asyncio
import logging
from zumrad_iis.services.stt.speech_recognizer import SpeechRecognizer

log = logging.getLogger(__name__)

class AltSpeechRecognizer(SpeechRecognizer):
    """
    Альтернативная версия класса для управления процессом распознавания речи.
    Здесь переписан метод `_wait_for_recognition_text`
    Проверяется состояние задачи распознавания речи в цикле while.
    Оставлено для тестов
    """
    async def _wait_for_recognition_text(self):
        try:
            while self.is_running:
                await asyncio.sleep(0.1) # Основной цикл ждет, обработка в callback
                if self._recognition_task and self._recognition_task.done():
                    try:
                        self._recognition_task.result() # Поднимет исключение, если оно было в задаче
                    except asyncio.CancelledError:
                        log.info("VoiceAssistant: Задача распознавания была отменена.")
                    except Exception as e:
                        log.error(f"VoiceAssistant: Задача распознавания завершилась с ошибкой: {e}")
                        self.is_running = False # Останавливаем, если задача распознавания упала
                    break # Выходим из основного цикла, если задача распознавания завершена

        except KeyboardInterrupt:
            log.info("\nVoiceAssistant: Завершение работы по Ctrl+C...")
            self.is_running = False
        except Exception as e: # Более общая обработка ошибок
            log.exception(f"VoiceAssistant: Произошла критическая ошибка в основном цикле: {e}")
            self.is_running = False
        finally:
            log.info("VoiceAssistant: Начало процедуры остановки...")
            self.is_running = False # Убедимся, что флаг установлен для всех компонентов

            if self._recognition_task and not self._recognition_task.done():
                log.info("VoiceAssistant: Отмена задачи распознавания...")
                self._recognition_task.cancel()
                try:
                    await self._recognition_task
                except asyncio.CancelledError:
                    log.info("VoiceAssistant: Задача распознавания успешно отменена.")
                except Exception as e:
                    log.error(f"VoiceAssistant: Ошибка при ожидании отмены задачи распознавания: {e}")

            self.audio_in.stop_capture()
            await self.destroy()
            log.info("VoiceAssistant: Приложение завершило работу.")