import sounddevice as sd
import logging
import vosk
import json
import queue
import asyncio

log = logging.getLogger("Simple_STT")

class Simple_STT:
    """
    The simple speech recognizer with base logic for testing.
    If test_simple_stt.py located inside of zumrad_iis module you can run its like:
    ```
    poetry run python -m zumrad_iis.services.stt.test_simple_stt
    ```
    else
    ```
    python3 test/services/stt/test_simple_stt.py
    ```
    """
    PATH_TO_SPEECH_RECOGNITION_MODEL = "stt_models/ru-RU" # loaded model should be placed here!
    SAMPLERATE = 16000
    BLOCK_SIZE = 8000
    CHANNELS = 1
    DEVICE_ID = None # None means default device in system
    DATA_TYPE_INT16 = "int16"
    
    def __init__(self):
        self.device_id = Simple_STT.DEVICE_ID
        self.model = None # later
        # self.samplerate = 16000
        self.q = queue.Queue()
        # self.blocksize = 8000
        # self.channels = 1

    def _check_capture_device(self, device_id):
        devices = sd.query_devices()
        name:str = ""
        log.info(f"Available speech capture devices:")
        if devices:
            for i, device in enumerate(devices):
                name = device.get("name", "") if isinstance(device, dict) else str(device)
                log.info(f"{i}: {name}")
        if device_id is not None and device_id >= len(devices):
            log.info(f"Device with ID {device_id} not found!")
            exit(1)
        current_device = sd.query_devices(device_id, 'input')
        if current_device:
            name = current_device.get("name", "") if isinstance(current_device, dict) else str(current_device)
            log.info(f"The device is in use: {name if device_id else 'Default device: ' + name}")
            
        log.info(f"Parameters of speech capturing: "
                f"Samplerate: {Simple_STT.SAMPLERATE}, "
                f"Block size: {Simple_STT.BLOCK_SIZE}, "
                f"Channels: {Simple_STT.CHANNELS}, ")

    def voice_listen(self):
        try:
            self.model = vosk.Model(Simple_STT.PATH_TO_SPEECH_RECOGNITION_MODEL)
            log.info(f"Model is loaded on path:{Simple_STT.PATH_TO_SPEECH_RECOGNITION_MODEL}")
            self._check_capture_device(self.device_id)
            def q_callback(indata, frames, time, status):
                self.q.put(bytes(indata))

            with sd.RawInputStream(
                callback=q_callback, 
                channels=Simple_STT.CHANNELS, 
                samplerate=Simple_STT.SAMPLERATE, 
                blocksize=Simple_STT.BLOCK_SIZE,
                device=self.device_id, 
                dtype=Simple_STT.DATA_TYPE_INT16
                ):
                log.info('Raw Input Strem...')
                rec = vosk.KaldiRecognizer(self.model, Simple_STT.BLOCK_SIZE)
                rec.SetWords(True)
                # sd.sleep(-20)
                while True:
                    data = self.q.get()
                    if rec.AcceptWaveform(data):
                        res = json.loads(rec.Result())["text"]
                        if res:
                            log.info(f"Said: {res}")
                    # else:
                    #     res = json.loads(rec.PartialResult())["partial"]
                    #     if res:
                    #         log.info(f"Stream: {res}")
        
        except (KeyboardInterrupt, asyncio.CancelledError):
            log.warning("Ctrl+C")
            raise KeyboardInterrupt
        except Exception as e:
            # log.error(f"Critical ERROR:\n{e}")  
            raise

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    stt = Simple_STT()
    log.info("Start voice listening...")
    try:
        stt.voice_listen()
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("The user halted the App.")
    except Exception as e:
        log.error(f"Critical ERROR at high App level:\n{e}")