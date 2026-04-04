import time
import re
import cv2
from PIL import Image
import google.generativeai as genai

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

    def __init__(self, face_node, sonar_node):
        self.face_node = face_node
        self.sonar_node = sonar_node

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
        "read this text", "what color is this", or asks to analyze
        their visual surroundings beyond just detecting people.
        """
        print("[LLM Tool] Executing: take_picture")
        # Returns a status flag; the Orchestrator handles the actual image attachment.
        return "picture_ready"


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
        }

    def route_command(self, transcript: str):
        """Returns the mapped function if matched, else returns None."""
        clean_text = transcript.lower().strip()
        for pattern, func in self.routes.items():
            if re.search(pattern, clean_text):
                return func
        return None


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

        # Initialize Gemini 2.5 Flash
        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            tools=[
                self.tools.describe_surroundings,
                self.tools.get_obstacle_distances,
                self.tools.take_picture,
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

        # Cache for the background video stream
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
            local_func = self.local_router.route_command(transcript)

            if local_func:
                print(
                    f"[Fast Path] Local Intent Matched! Executing: {local_func.__name__}"
                )
                result_text = local_func()
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

                    # Handle Standard Tools
                    if function_name == "describe_surroundings":
                        result = self.tools.describe_surroundings()
                        response = self.chat.send_message(
                            {
                                "function_response": {
                                    "name": function_name,
                                    "response": {"result": result},
                                }
                            }
                        )

                    elif function_name == "get_obstacle_distances":
                        result = self.tools.get_obstacle_distances()
                        response = self.chat.send_message(
                            {
                                "function_response": {
                                    "name": function_name,
                                    "response": {"result": result},
                                }
                            }
                        )

                    # Handle Multimodal Visual Tool
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
