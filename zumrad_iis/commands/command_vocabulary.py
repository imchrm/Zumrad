import logging
from typing import Dict

log: logging.Logger = logging.getLogger(__name__) 

class CommandVocabulary:
    """
    A data class where each phrase is associated with a command name.
    
    Attributes:
        commands (list[str]): A list of command names.
        phrases (Dict[str, str]): A dictionary where keys are phrases and values are command names.
    """
    CMD_QUIT: str = "quit"
    CMD_ATTENTION_ONE: str = "attention_one"
    CMD_ATTENTION_TWO: str = "attention_two"
    CMD_DANGER_OF_FIRE: str = "danger_of_fire"
    CMD_LAUNCH_VIDEO_PLAYER: str = "launch_video_player"
    CMD_WHAT_TIME_IS_IT: str = "what_time_is"
    CMD_REPEAT_ON: str = "repeat"
    CMD_REPEAT_OFF: str = "stop"
    
    def __init__(self) -> None:
        self.commands: list[str] = [CommandVocabulary.CMD_QUIT, 
                                CommandVocabulary.CMD_ATTENTION_ONE, 
                                CommandVocabulary.CMD_ATTENTION_TWO, 
                                CommandVocabulary.CMD_DANGER_OF_FIRE, 
                                CommandVocabulary.CMD_LAUNCH_VIDEO_PLAYER, 
                                CommandVocabulary.CMD_WHAT_TIME_IS_IT, 
                                CommandVocabulary.CMD_REPEAT_ON, 
                                CommandVocabulary.CMD_REPEAT_OFF]
        self.phrase_map: Dict[str, str] = {}
        
    def __repr__(self) -> str:
        data: str = 'CommandVocabulary phrase_map:\n'
        for phrase in self.phrase_map:
            data += f"  {phrase}: {self.phrase_map[phrase]}\n"
        return data
    def __str__(self) -> str:
        data: str = 'CommandVocabulary phrase_map:\n'
        for phrase in self.phrase_map:
            data += f"  {phrase}: {self.phrase_map[phrase]}\n"
        return data
