from src.core.event_bus import shared_event_bus

class FaceRecognition:
    def __init__(self):
        shared_event_bus.subscribe("reload_faces", self._load_known_faces)

    def _load_known_faces(self):
        print("Reloading faces...")