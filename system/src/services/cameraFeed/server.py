import socket
import struct
import cv2
import threading
import queue
from src.core.event_bus import shared_event_bus
from src.core.events import RenderedFrameEvent

class NetworkServerNode(threading.Thread):
    def __init__(self, port: int = 9999):
        super().__init__(daemon=True)
        self.port = port
        self.frame_queue = queue.Queue(maxsize=10) 
        self.total_frames_received = 0 # DEBUG COUNTER
        
        # Subscribe to the shared bus
        shared_event_bus.subscribe("rendered_frame", self.on_rendered_frame)

    def on_rendered_frame(self, event: RenderedFrameEvent):
        self.total_frames_received += 1
        
        if not self.frame_queue.full():
            self.frame_queue.put(event.frame)
            # DEBUG: Print once roughly every second
            if self.total_frames_received % 30 == 0:
                print(f"[Network-Debug] Enqueued frame. Queue size: {self.frame_queue.qsize()}/10")
        else:
            # DEBUG: Let us know if the network is too slow and we are dropping frames
            if self.total_frames_received % 30 == 0:
                print("[Network-Debug] WARNING: Queue FULL! Dropping frame to maintain real-time feed.")

    def run(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', self.port))
        server_socket.listen(1)
        
        print(f"[Network] Server listening on port {self.port}...")

        while True:
            try:
                client_socket, addr = server_socket.accept()
                print(f"[Network] Client connected from {addr}")
                
                # Clear out old frames from before the client connected
                while not self.frame_queue.empty():
                    self.frame_queue.get()
                    
                print("[Network-Debug] Old frames cleared. Entering transmission loop.")
                frames_sent = 0

                while True:
                    # This line BLOCKS until a frame is available in the queue
                    frame = self.frame_queue.get() 
                    
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if not ret: 
                        print("[Network-Debug] ERROR: cv2.imencode failed to compress frame!")
                        continue
                        
                    data = buffer.tobytes()
                    data_len = len(data)
                    
                    # Pack the 4-byte size header, then the image bytes
                    message = struct.pack(">L", data_len) + data
                    client_socket.sendall(message)
                    
                    frames_sent += 1
                    
                    # DEBUG: Confirm data is successfully leaving the Pi
                    if frames_sent % 30 == 0:
                        print(f"[Network-Debug] Successfully sent {frames_sent} frames. Latest packet size: {data_len} bytes")
                    
            except (ConnectionResetError, BrokenPipeError):
                print("[Network] Client disconnected. Waiting for new connection...")
            except Exception as e:
                print(f"[Network] Error: {e}")
            finally:
                if 'client_socket' in locals():
                    client_socket.close()
                    print("[Network-Debug] Socket closed cleanly.")
