import os
import time
import json
from abc import ABC, abstractmethod


def _is_invalid_cached_match_payload(file_path: str, file_data) -> bool:
    normalized_path = file_path.replace("\\", "/")
    if "/match/" not in normalized_path:
        return False

    if not isinstance(file_data, list) or len(file_data) != 1 or not isinstance(file_data[0], dict):
        return False

    payload = file_data[0]
    match = payload.get("match")
    if not isinstance(match, dict):
        return False

    team1_candidate = match.get("team1")
    team2_candidate = match.get("team2")
    team1 = team1_candidate if isinstance(team1_candidate, dict) else {}
    team2 = team2_candidate if isinstance(team2_candidate, dict) else {}

    return all(
        value is None
        for value in (
            match.get("date"),
            match.get("hour"),
            match.get("event"),
            payload.get("demoUrl"),
            team1.get("name"),
            team2.get("name"),
        )
    )


class Condition(ABC):
    @abstractmethod
    def __init__(self, *args, **kwargs) -> None:
        pass
    
    @abstractmethod
    def check(self) -> bool:
        pass

# Check if a file is older than a certain number of hours
class FileTimeCondition(Condition):
    def __init__(self, file_path: str, hours: int = 1) -> None:
        self.file_path = file_path
        self.hours = hours
    
    def check(self) -> bool:
        if not os.path.exists(self.file_path):
            return True
        file_age_in_seconds = time.time() - os.path.getmtime(self.file_path)
        return file_age_in_seconds > (3600 * self.hours)


class JsonFileEmptyCondition(Condition):
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        
    def check(self) -> bool:
        if not os.path.exists(self.file_path):
            return True

        try:
            with open(self.file_path, "r") as file:
                file_data = json.load(file)
                return file_data == [] or _is_invalid_cached_match_payload(self.file_path, file_data)
        except Exception as e:
            print(f"Error loading JSON file: {e}")
            return True
        
class FileExistsCondition(Condition):
    def __init__(self, file_path:str) -> None:
        self.file_path = file_path
        
    def check(self) -> bool:
        return os.path.exists(self.file_path)
