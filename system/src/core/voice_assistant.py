import speech_recognition as sr
from src.hardware.headset import HeadsetCommandListener
from src.core.event_bus import shared_event_bus  # Import the megaphone


class VoiceAssistant:
    def __init__(self):
        # Notice: We don't need the speech_client or the models here anymore!
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 2.0
        self.listener = HeadsetCommandListener(
            on_command_trigger=self._handle_button_press
        )

    def start(self):
        self.listener.start()
        print("[Voice Assistant] Running in background.")

    def stop(self):
        self.listener.stop()

    def _handle_button_press(self):
        try:
            with sr.Microphone() as source:
                print("\n[Voice Assistant] 🔴 Listening...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=15)

                print("[Voice Assistant] ⏹️ Transcribing...")
                transcript = self.recognizer.recognize_google(audio).lower().strip()
                print(f"[Voice Assistant] Heard: '{transcript}'")

                # 📢 BROADCAST THE EVENT TO ANYONE WHO IS LISTENING
                if transcript:
                    shared_event_bus.publish(
                        event_type="voice_command", data=transcript
                    )

        except Exception as e:
            print(f"[Voice Assistant] Error: {e}")
