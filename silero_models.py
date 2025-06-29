#@title Install dependencies

# pip install ipython -- необходимая библиотека для отображения аудио в Jupyter (IPython.display)
import torch
from pprint import pprint
from omegaconf import OmegaConf
from IPython.display import Audio, display

"""
This script downloads the latest Silero TTS models configuration file and lists available languages and models.
It uses the `torch.hub` to download the models configuration and `OmegaConf` to parse it.
It also provides a function to display the audio in Jupyter notebooks.
"""

torch.hub.download_url_to_file('https://raw.githubusercontent.com/snakers4/silero-models/master/models.yml',
                            'latest_silero_models.yml',
                            progress=False)
models = OmegaConf.load('latest_silero_models.yml')

# see latest avaiable models
available_languages = list(models.tts_models.keys())
print(f'Available languages {available_languages}')

for lang in available_languages:
    _models = list(models.tts_models.get(lang).keys())
    print(f'Available models for {lang}: {_models}')