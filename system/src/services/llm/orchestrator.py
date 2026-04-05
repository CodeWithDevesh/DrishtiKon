import os
import time
import re
import cv2
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

# Project-specific imports
from src.core.event_bus import shared_event_bus
from src.core.events import RawFrameEvent
from src.speech.client import SpeechClient


# ==========================================
# 1. HARDWARE TOOLS SCHEMA
# ==========================================
class SystemTools:
    """
    These methods are exposed to the LLM. The docstrings are critical as they
    tell the LLM exactly when and how to use them.
    """

    def __init__(self, face_node, sonar_node, snapshot_node, ocr_node, nav_node):
        self.face_node = face_node
        self.sonar_node = sonar_node
        self.snapshot_node = snapshot_node
        self.ocr_node = ocr_node
        self.nav_node = nav_node  # The ObjectDetectionNode

    def describe_surroundings(self) -> str:
        """
        Takes a visual sweep of the surroundings to describe the people currently
        visible to the camera. Use this when the user asks "who is around me",
        "describe the scene", or asks about people.
        """
        print("[LLM Tool] Executing: describe_surroundings")
        return self.face_node.describe_scene()

    def get_obstacle_distances(self) -> str:
        """
        Fetches the current distance of physical obstacles from the left, center,
        and right ultrasonic sensors in centimeters. Use this if the user asks
        how close they are to a wall or object.
        """
        print("[LLM Tool] Executing: get_obstacle_distances")
        left, center, right = self.sonar_node.get_current_readings()
        return f"Left: {left}cm, Center: {center}cm, Right: {right}cm"

    def take_picture(self) -> str:
        """
        Captures an image from the user's point-of-view camera.
        Call this tool if the user asks "what is in front of me",
        "what color is this", or asks to analyze their visual surroundings.
        """
        print("[LLM Tool] Executing: take_picture")
        # Returns a status flag; the Orchestrator handles the actual image attachment.
        return "picture_ready"

    def register_person(self, name: str) -> str:
        """
        Starts the process of registering a new face in the database.
        Call this if the user asks to "register" someone or "add a person" to the system.
        You must provide the 'name' of the person extracted from the user's prompt.
        """
        print(f"[LLM Tool] Executing: register_person for '{name}'")
        shared_event_bus.publish("registration_request", data=name)
        return f"Successfully initiated registration for {name}."

    def save_snapshot_to_cloud(self) -> str:
        """
        Captures the current camera frame and uploads it permanently to cloud storage.
        Call this tool when the user explicitly asks to "save a snap", "take a snapshot",
        or "upload a photo".
        """
        print("[LLM Tool] Executing: save_snapshot_to_cloud")
        return self.snapshot_node.take_and_upload_snap()

    def read_text(self) -> str:
        """
        Scans the camera feed for printed text, handwriting, or signs and reads it aloud.
        Call this tool if the user asks you to "read this", "scan the text", or
        "what does this say".
        """
        print("[LLM Tool] Executing: read_text")
        return self.ocr_node.perform_ocr()

    def enable_obstacle_detection(self) -> str:
        """
        Turns on the continuous ultrasonic obstacle detection system.
        Call this tool if the user says "turn on object detection",
        "enable obstacle guidance", or "activate the sensors".
        """
        print("[LLM Tool] Executing: enable_obstacle_detection")
        return self.nav_node.turn_on()

    def disable_obstacle_detection(self) -> str:
        """
        Turns off the continuous ultrasonic obstacle detection system.
        Call this tool if the user says "turn off object detection",
        "disable obstacle guidance", or "stop the sensors".
        """
        print("[LLM Tool] Executing: disable_obstacle_detection")
        return self.nav_node.turn_off()


# ==========================================
# 2. FAST-PATH LOCAL ROUTER
# ==========================================
class LocalCommandRouter:
    """
    Intercepts highly predictable voice commands to execute them locally
    in milliseconds, saving LLM API costs and avoiding cloud latency.
    """

    def __init__(self, tools: SystemTools):
        self.tools = tools

        # Map RegEx patterns directly to SystemTools functions
        self.routes = {
            r"(who is|who's) (in front of me|around me|here)": self.tools.describe_surroundings,
            r"describe (the scene|surroundings)": self.tools.describe_surroundings,
            r"(check|read) (sensors|distance|sonar)": self.tools.get_obstacle_distances,
            r"how far is the (wall|obstacle)": self.tools.get_obstacle_distances,
            r"(?:register|add person(?: called| named)?)\s+(?P<name>[a-z\s]+)": self.tools.register_person,
            r"(take|save|upload) a (snap|snapshot|photo|picture)": self.tools.save_snapshot_to_cloud,
            r"(read|scan) (this|the text|text)|what does this say": self.tools.read_text,
            r"(turn|switch|power) on (object detection|obstacle guidance|guidance)": self.tools.enable_obstacle_detection,
            r"(turn|switch|power) (off|of) (object detection|obstacle guidance|guidance)": self.tools.disable_obstacle_detection,
        }

    def route_command(self, transcript: str):
        """Returns a tuple of (function, kwargs_dictionary) if matched, else (None, None)."""
        clean_text = transcript.lower().strip()
        for pattern, func in self.routes.items():
            match = re.search(pattern, clean_text)
            if match:
                kwargs = match.groupdict()
                return func, kwargs
        return None, None


# ==========================================
# 3. MAIN ORCHESTRATOR NODE
# ==========================================
class LLMOrchestratorNode:
    """
    Listens to voice commands, intercepts local intents, and routes complex
    queries to Gemini while maintaining multimodal context.
    """

    def __init__(self, speech_client: SpeechClient, system_tools: SystemTools):
        self.speech = speech_client
        self.tools = system_tools
        self.local_router = LocalCommandRouter(self.tools)

        print("[LLM] Initializing Orchestrator with Hardware Tools...")

        # Securely load API Key
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "[Error] GEMINI_API_KEY is missing! Please set it in your .env file."
            )

        genai.configure(api_key=api_key)

        # Initialize Gemini 2.5 Flash
        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            tools=[
                self.tools.describe_surroundings,
                self.tools.get_obstacle_distances,
                self.tools.take_picture,
                self.tools.register_person,
                self.tools.save_snapshot_to_cloud,
                self.tools.read_text,
                self.tools.enable_obstacle_detection,
                self.tools.disable_obstacle_detection,
            ],
            system_instruction=(
                "You are the autonomous intelligence core of an assistive robotics wearable. "
                "Your output is spoken directly to the user via TTS. NEVER use markdown, "
                "bullet points, or special characters. Keep answers brief, conversational, "
                "and immediately actionable. "
                "CRITICAL DIRECTIVE: You operate with total autonomy. NEVER ask the user for "
                "permission to use your tools. If a query requires sensor data or visual context, "
                "immediately execute the necessary function. "
                "GENERAL CONVERSATION: You are also a friendly, general-knowledge companion. "
                "If the user asks a general question, wants to chat, or asks for information "
                "that does not require hardware tools, answer them normally and helpfully based "
                "on your internal knowledge."
            ),
        )
        self.chat = self.model.start_chat()
        self._latest_frame = None

        # Subscriptions
        shared_event_bus.subscribe("voice_command", self._on_voice_command)
        shared_event_bus.subscribe("raw_frame", self._on_raw_frame)

    def _on_raw_frame(self, event: RawFrameEvent):
        """Silently cache the most recent camera frame."""
        self._latest_frame = event.frame

    def _on_voice_command(self, transcript: str):
        print(f"\n[User Audio] -> '{transcript}'")

        try:
            # ---------------------------------------------------------
            # THE FAST PATH (Local Interception)
            # ---------------------------------------------------------
            local_func, kwargs = self.local_router.route_command(transcript)

            if local_func:
                print(
                    f"[Fast Path] Local Intent Matched! Executing: {local_func.__name__} with args: {kwargs}"
                )

                # Execute dynamically, passing kwargs if they were extracted (like 'name')
                result_text = local_func(**kwargs) if kwargs else local_func()

                print(f"[Local Output] -> '{result_text}'")
                self.speech.speak_text(result_text)
                return  # Exit early, bypassing the LLM

            # ---------------------------------------------------------
            # THE SLOW PATH (LLM Fallback)
            # ---------------------------------------------------------
            print("[Slow Path] No local intent matched. Routing to LLM...")
            response = self.chat.send_message(transcript)

            for part in response.parts:
                if fn := part.function_call:
                    function_name = fn.name
                    print(f"[*] LLM requested function: {function_name}")

                    # --- HANDLE STANDARD & NO-ARGUMENT TOOLS ---
                    if function_name in [
                        "describe_surroundings",
                        "get_obstacle_distances",
                        "save_snapshot_to_cloud",
                        "read_text",
                        "enable_obstacle_detection",
                        "disable_obstacle_detection",
                    ]:
                        tool_func = getattr(self.tools, function_name)
                        result = tool_func()
                        response = self.chat.send_message(
                            {
                                "function_response": {
                                    "name": function_name,
                                    "response": {"result": result},
                                }
                            }
                        )

                    # --- HANDLE ARGUMENT TOOLS ---
                    elif function_name == "register_person":
                        # Safely extract the argument the LLM generated
                        person_name = fn.args.get("name", "Unknown Person")
                        result = self.tools.register_person(name=person_name)
                        response = self.chat.send_message(
                            {
                                "function_response": {
                                    "name": function_name,
                                    "response": {"result": result},
                                }
                            }
                        )

                    # --- HANDLE MULTIMODAL VISUAL TOOL ---
                    elif function_name == "take_picture":
                        if self._latest_frame is None:
                            response = self.chat.send_message(
                                {
                                    "function_response": {
                                        "name": function_name,
                                        "response": {
                                            "result": "Error: Camera is currently offline."
                                        },
                                    }
                                }
                            )
                        else:
                            print("[*] Attaching camera frame to LLM context...")
                            # Convert OpenCV BGR to PIL RGB for Gemini
                            rgb_frame = cv2.cvtColor(
                                self._latest_frame, cv2.COLOR_BGR2RGB
                            )
                            pil_img = Image.fromarray(rgb_frame)

                            # MAGIC HAPPENS HERE: Array with the function response dict AND the image
                            response = self.chat.send_message(
                                [
                                    {
                                        "function_response": {
                                            "name": function_name,
                                            "response": {
                                                "status": "Success. Image attached."
                                            },
                                        }
                                    },
                                    pil_img,
                                ]
                            )

            # Finalize and speak the LLM's response
            final_answer = response.text
            print(f"[LLM Output] -> '{final_answer}'")
            self.speech.speak_text(final_answer)

        except Exception as e:
            print(f"[Error] Pipeline failed: {e}")
            self.speech.speak_text("I'm sorry, I encountered an error processing that.")
