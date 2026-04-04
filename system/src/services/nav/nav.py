import threading
import re  # <-- Restored: Needed to strip HTML from Google Maps instructions
from flask import Flask, request, jsonify
from flask_cors import CORS
import googlemaps

class NavServerNode:
    def __init__(self, api_key: str, port: int = 7000):
        self.app = Flask(__name__)
        CORS(self.app)
        
        # Safe API Key handling
        if not api_key:
            raise ValueError("Google Maps API key is required to start the NavServerNode.")
        self.gmaps = googlemaps.Client(key=api_key)
        
        self.port = port
        
        # State shared with the aggregator
        self.nav_state = {
            "destination": None,
            "last_instruction": "Waiting for destination..."
        }

        # Define routes
        self._setup_routes()

    def _setup_routes(self):
        @self.app.route('/set_destination', methods=['POST'])
        def set_dest():
            # Safely parse JSON
            data = request.get_json()
            if not data or 'address' not in data:
                return jsonify({"error": "Missing 'address' in request body"}), 400
                
            self.nav_state["destination"] = data.get('address')
            print(f"[NavServer] Destination locked to: {self.nav_state['destination']}")
            return jsonify({"status": "Target Locked", "destination": self.nav_state["destination"]}), 200

        @self.app.route('/update_and_get', methods=['POST'])
        def update_and_get():
            data = request.get_json()
            
            # Safely check if lat/lng exist
            if not data or 'lat' not in data or 'lng' not in data:
                return jsonify({"error": "Missing 'lat' or 'lng' in request body"}), 400
                
            lat, lng = data['lat'], data['lng']
            
            # --- RESTORED GOOGLE MAPS LOGIC ---
            if self.nav_state["destination"]:
                try:
                    # Pi calls Google Maps for the directions
                    res = self.gmaps.directions(
                        f"{lat},{lng}", 
                        self.nav_state["destination"], 
                        mode="walking"
                    )
                    if res:
                        # Grab the very next step
                        step = res[0]['legs'][0]['steps'][0]
                        # Use regex to strip out HTML tags like <b> and </b>
                        clean_instruction = re.sub('<[^<]+>', '', step['html_instructions'])
                        self.nav_state["last_instruction"] = clean_instruction
                        
                except Exception as e:
                    print(f"[NavServer] Maps Error: {e}")
            
            return jsonify({"instruction": self.nav_state["last_instruction"]}), 200

    def run(self):
        print(f"[NavServer] Starting Flask API on port {self.port}...")
        # Running with use_reloader=False is critical when inside a thread
        self.app.run(host='0.0.0.0', port=self.port, debug=False, use_reloader=False)

    def start(self):
        # Start Flask in a background thread
        server_thread = threading.Thread(target=self.run, daemon=True)
        server_thread.start()
