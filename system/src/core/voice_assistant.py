import speech_recognition as sr
import os
from playsound import playsound  
from src.hardware.headset import HeadsetCommandListener
from src.core.event_bus import shared_event_bus 

class VoiceAssistant:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 2.0
        self.listener = HeadsetCommandListener(
            on_command_trigger=self._handle_button_press
        )
        # Path to your notification sound
        self.activation_sound = "assets/start_sound.mp3" 

    def start(self):
        self.listener.start()
        print("[Voice Assistant] Running in background.")

    def stop(self):
        self.listener.stop()

    def _handle_button_press(self):
        """Internal callback for the headset button."""
        self.trigger_listen()

    # Inside your VoiceAssistant class, update the trigger_listen method:

    def trigger_listen(self):
        try:
            if os.path.exists(self.activation_sound):
                playsound(self.activation_sound)

            with sr.Microphone() as source:
                print("\n[Voice Assistant] 🔴 Listening...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=15)
                transcript = self.recognizer.recognize_google(audio).lower().strip()
                print(f"[Voice Assistant] Heard: '{transcript}'")

                if transcript:
                    # Logic for Registration
                    if "register" in transcript or "add person" in transcript:
                        # Extract name: "register Soumyajeet" -> "Soumyajeet"
                        name = transcript.replace("register", "").replace("add person", "").strip()
                        if name:
                            # Publish a specific event for the Registrar to catch
                            shared_event_bus.publish("registration_request", data=name)
                    
                    # Still publish the general command for other nodes
                    shared_event_bus.publish(event_type="voice_command", data=transcript)

        except Exception as e:
            print(f"[Voice Assistant] Error: {e}")