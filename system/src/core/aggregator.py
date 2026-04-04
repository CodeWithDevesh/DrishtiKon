import time
import threading
import cv2

from src.core.events import RawFrameEvent, ModelResultEvent, RenderedFrameEvent
from src.core.event_bus import shared_event_bus

class AggregatorNode:
    """
    Central Vision Hub: Subscribes to raw frames and MULTIPLE models, 
    draws all bounding boxes, and publishes the final composed image.
    """
    def __init__(self, expected_models: list[str]):
        self.expected_models = expected_models
        self.frame_buffer = {}
        self.lock = threading.Lock()
        
        shared_event_bus.subscribe("raw_frame", self.on_raw_frame)
        shared_event_bus.subscribe("model_result", self.on_model_result)

    def on_raw_frame(self, event: RawFrameEvent):
        with self.lock:
            if event.frame_id not in self.frame_buffer:
                self.frame_buffer[event.frame_id] = {
                    "frame": None,
                    "timestamp": time.time(),
                    "results": {} 
                }
            self.frame_buffer[event.frame_id]["frame"] = event.frame.copy()
            self._check_and_render(event.frame_id)

    def on_model_result(self, event: ModelResultEvent):
        with self.lock:
            if event.frame_id not in self.frame_buffer:
                self.frame_buffer[event.frame_id] = {
                    "frame": None,
                    "timestamp": time.time(),
                    "results": {}
                }
                
            self.frame_buffer[event.frame_id]["results"][event.model_name] = event.data
            self._check_and_render(event.frame_id)

    def _check_and_render(self, frame_id: int):
        data = self.frame_buffer[frame_id]
        if data["frame"] is None:
            return 
            
        # SYNCHRONIZATION BARRIER: Wait for all expected models
        for model_name in self.expected_models:
            if model_name not in data["results"]:
                return 
                
        # Extract data
        ready_data = self.frame_buffer.pop(frame_id)
        frame = ready_data["frame"]
        
        # Draw all bounding boxes from all models
        for model_name, model_results in ready_data["results"].items():
            for item in model_results:
                x1, y1, x2, y2 = item["box"]
                label = item["label"]
                color = item.get("color", (255, 165, 0)) # Default to orange
                
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.rectangle(frame, (x1, y2 - 35), (x2, y2), color, cv2.FILLED)
                cv2.putText(frame, label, (x1 + 6, y2 - 6), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)

        cv2.putText(
            frame, f"System Active ({len(self.expected_models)} Models)", (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2
        )

        # Broadcast the finalized image to the network streamer
        shared_event_bus.publish(
            "rendered_frame", 
            RenderedFrameEvent(frame_id, frame),
            run_async=False
        )
        
        # Memory cleanup
        current_time = time.time()
        stale = [fid for fid, fd in self.frame_buffer.items() if current_time - fd["timestamp"] > 1.0]
        for fid in stale: del self.frame_buffer[fid]
