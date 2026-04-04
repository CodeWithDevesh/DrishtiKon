import time
import threading
import evdev
from evdev import categorize, ecodes


class HeadsetCommandListener:
    """
    Listens for Bluetooth headset button presses in the background.
    Triggers a callback function when the Play/Pause button is pressed.
    """

    def __init__(self, on_command_trigger: callable):
        self.on_command_trigger = on_command_trigger
        self.device = self._find_headset_device()
        self.is_running = False
        self.last_trigger_time = 0.0

    def _find_headset_device(self) -> evdev.InputDevice | None:
        """Finds the Bluetooth AVRCP device (e.g., Sony WH-CH720N)."""
        try:
            for path in evdev.list_devices():
                dev = evdev.InputDevice(path)
                if "AVRCP" in dev.name or "WH-CH720N" in dev.name:
                    return dev
        except Exception as e:
            print(f"[Warning] Could not scan input devices: {e}")
        return None

    def start(self):
        """Starts the background listener thread."""
        if not self.device:
            print(
                "[Hardware Error] No Bluetooth headset found. Voice commands disabled."
            )
            return

        self.is_running = True
        # Daemon=True ensures this thread dies instantly when the main app closes
        listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        listener_thread.start()
        print(f"[Hardware] Headset listener active on: {self.device.name}")

    def stop(self):
        """Signals the background thread to shut down."""
        self.is_running = False

    def _listen_loop(self):
        """The blocking loop that waits for hardware events."""
        try:
            # Grab exclusive access so the OS media player doesn't steal the button press
            self.device.grab()

            for event in self.device.read_loop():
                if not self.is_running:
                    break

                if event.type == ecodes.EV_KEY:
                    key_event = categorize(event)

                    # keystate 1 == Button Down (Pressed)
                    if key_event.keystate == 1:
                        # Catching both PLAY and PAUSE since Sony toggles them
                        if key_event.keycode in ["KEY_PLAYCD", "KEY_PAUSECD"]:
                            current_time = time.time()

                            # Debounce: Prevent double-triggers if pressed rapidly within 1.5s
                            if current_time - self.last_trigger_time > 1.5:
                                self.last_trigger_time = current_time

                                # Fire the callback in its own thread so we don't freeze the listener
                                threading.Thread(
                                    target=self.on_command_trigger, daemon=True
                                ).start()

        except Exception as e:
            print(f"\n[Hardware Error] Headset listener disconnected: {e}")
        finally:
            try:
                # Always release the device on exit
                self.device.ungrab()
            except Exception:
                pass
