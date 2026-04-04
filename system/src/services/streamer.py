import cv2
from flask import Flask, Response
from src.core.event_bus import shared_event_bus
import threading

app = Flask(__name__)
last_frame = None
frame_lock = threading.Lock()


def on_raw_frame(event):
    global last_frame
    with frame_lock:
        last_frame = event.frame

shared_event_bus.subscribe("raw_frame", on_raw_frame)

def generate_mjpeg():
    while True:
        with frame_lock:
            if last_frame is None:
                continue
            # Encode to JPEG for the web
            ret, buffer = cv2.imencode('.jpg', last_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ret:
                continue
            frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(generate_mjpeg(), 
                    mimetype='multipart/x-mixed-replace; boundary=frame')

def start_http_streamer(port=8000):
    # run_reloader=False is mandatory when running in a thread
    app.run(host='0.0.0.0', port=port, threaded=True, debug=False, use_reloader=False)