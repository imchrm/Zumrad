import logging
from typing import Dict, TypeAlias

log: logging.Logger = logging.getLogger(__name__) 

KeyCommand: TypeAlias = str
ValueCommand: TypeAlias = str
VocabularyMap: TypeAlias = Dict[KeyCommand, ValueCommand]


class Vocabulary:
    def __init__(self, vocabulary: list[str], vocabulary_map: VocabularyMap) -> None:
        self.vocabulary: list[str] = vocabulary
        self.vocabulary_map: VocabularyMap = vocabulary_map  # Its should be inflated later in config.py
        
    def __repr__(self) -> str:
        data: str = 'Vocabulary map:\n'
        for key in self.vocabulary_map:
            data += f"  {key}: {self.vocabulary_map[key]}\n"
        return data
    def __str__(self) -> str:
        data: str = 'Vocabulary map:\n'
        for key in self.vocabulary_map:
            data += f"  {key}: {self.vocabulary_map[key]}\n"
        return data


class CommandVocabulary(Vocabulary):
    """
    A data class where each phrase is associated with a command name.
    
    Attributes:
        commands (list[str]): A list of command names.
        phrases (Dict[str, str]): A dictionary where keys are phrases and values are command names.
    """
    
    
    def __init__(self, vocabulary: list[str], vocabulary_map: VocabularyMap) -> None:
        super().__init__(vocabulary, vocabulary_map)
