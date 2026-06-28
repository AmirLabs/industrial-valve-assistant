from typing import List, Dict

class MemoryManager:
    """Manages in-memory chat history with a sliding window mechanism."""
    
    def __init__(self, window_size: int = 8):
        self._storage: Dict[str, List[Dict[str, str]]] = {}
        self.window_size = window_size

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """Retrieves the last N messages for a given session_id based on window_size."""
        history = self._storage.get(session_id, [])
        return history[-self.window_size:]

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Appends a new message molecule (user/assistant) to the session storage."""
        if session_id not in self._storage:
            self._storage[session_id] = []
          
        self._storage[session_id].append({
            "role": role,
            "content": content
        })

    def clear_history(self, session_id: str) -> None:
        """Flushes the entire chat history for a specific session."""
        if session_id in self._storage:
            del self._storage[session_id]