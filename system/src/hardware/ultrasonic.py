import time
import threading
from dataclasses import dataclass

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    print("[Warning] RPi.GPIO not found. Using simulated ultrasonic data.")
    GPIO_AVAILABLE = False

from src.core.events import UltrasonicEvent
from src.core.event_bus import shared_event_bus

@dataclass
class SensorConfig:
    name: str
    trig: int
    echo: int

class UltrasonicNode(threading.Thread):
    """
    Background daemon that reads a Left, Center, and Right ultrasonic array.
    Publishes distances to the event bus at ~10Hz.
    Includes strict timeouts to diagnose wiring faults immediately.
    """
    def __init__(self, left_pins=(5, 6), center_pins=(13, 19), right_pins=(26, 21)):
        super().__init__(daemon=True)
        
        self.sensors = [
            SensorConfig("Left", left_pins[0], left_pins[1]),
            SensorConfig("Center", center_pins[0], center_pins[1]),
            SensorConfig("Right", right_pins[0], right_pins[1])
        ]
        
        # We cap the reading frequency to avoid soundwave collision/echo crossover
        self.read_interval_s = 0.1  # 10 FPS
        
        if GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for s in self.sensors:
                GPIO.setup(s.trig, GPIO.OUT)
                GPIO.setup(s.echo, GPIO.IN)
                GPIO.output(s.trig, False)
            
            print("[Hardware] Ultrasonic Array initialized. Settling sensors...")
            time.sleep(1) # Allow sensors to settle

    def _read_distance(self, sensor: SensorConfig) -> float:
        if not GPIO_AVAILABLE:
            return 1000.0 # Return fake 1 meter if testing on PC

        # 1. Fire the 10-microsecond trigger pulse
        GPIO.output(sensor.trig, True)
        time.sleep(0.00001)
        GPIO.output(sensor.trig, False)

        timeout_start = time.time()
        pulse_start = time.time()
        
        # 2. Wait for ECHO pin to go HIGH
        while GPIO.input(sensor.echo) == 0:
            pulse_start = time.time()
            if pulse_start - timeout_start > 0.04: # 40ms timeout (~6 meters)
                print(f"[HW-ERROR] {sensor.name} Sensor: ECHO never went HIGH. "
                      f"(Check TRIG wiring, or sensor lost VCC/GND)")
                return -1.0
                
        # 3. Wait for ECHO pin to go LOW
        pulse_end = time.time()
        timeout_start = time.time()
        while GPIO.input(sensor.echo) == 1:
            pulse_end = time.time()
            if pulse_end - timeout_start > 0.04:
                print(f"[HW-ERROR] {sensor.name} Sensor: ECHO never went LOW. "
                      f"(Check ECHO resistor divider, or ECHO wire is shorted to 3.3v)")
                return -1.0

        # 4. Math: Speed of sound is 34300 cm/s. 
        # Divide by 2 because the wave travels there and back.
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        return round(distance, 2)

    def run(self):
        print("[Hardware] Ultrasonic Array streaming started.")
        while True:
            # Sequentially read to avoid physical sound wave interference
            left_dist = self._read_distance(self.sensors[0])
            center_dist = self._read_distance(self.sensors[1])
            right_dist = self._read_distance(self.sensors[2])

            # Publish to the bus for the Nav system or Vision models to use!
            # run_async=False prevents thread exhaustion for high-frequency hardware events
            shared_event_bus.publish(
                "ultrasonic_data", 
                UltrasonicEvent(left_dist, center_dist, right_dist),
                run_async=False 
            )

            time.sleep(self.read_interval_s)
