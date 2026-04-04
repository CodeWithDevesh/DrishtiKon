import time
import threading
import platform

IS_LINUX = platform.system() == "Linux"

# =========================
# Linux (Raspberry Pi)
# =========================
if IS_LINUX:
    try:
        import evdev
        from evdev import categorize, ecodes
        EVDEV_AVAILABLE = True
    except ImportError:
        EVDEV_AVAILABLE = False
else:
    EVDEV_AVAILABLE = False

# =========================
# Windows Support
# =========================
if not EVDEV_AVAILABLE:
    try:
        from pynput import keyboard as pynput_keyboard
        WINDOWS_MEDIA = True
    except ImportError:
        WINDOWS_MEDIA = False


class HeadsetCommandListener:
    def __init__(self, on_command_trigger):
        self.on_command_trigger = on_command_trigger
        self.is_running = False
        self.last_trigger_time = 0.0

        if EVDEV_AVAILABLE:
            self.device = self._find_headset_device()
        else:
            self.device = None

    # =========================
    # Find headset (Linux)
    # =========================
    def _find_headset_device(self):
        try:
            for path in evdev.list_devices():
                dev = evdev.InputDevice(path)
                if "AVRCP" in dev.name or "WH-CH720N" in dev.name:
                    return dev
        except Exception as e:
            print(f"[Warning] Device scan failed: {e}")
        return None

    # =========================
    # Start Listener
    # =========================
    def start(self):
        self.is_running = True

        if EVDEV_AVAILABLE:
            if not self.device:
                print("❌ No Bluetooth headset found (Linux)")
                return

            threading.Thread(target=self._listen_linux, daemon=True).start()
            print(f"🎧 Linux headset active: {self.device.name}")

        else:
            threading.Thread(target=self._listen_windows, daemon=True).start()
            print("💻 Windows mode: Listening for headset/media button")

    def stop(self):
        self.is_running = False

    # =========================
    # Linux Listener
    # =========================
    def _listen_linux(self):
        try:
            self.device.grab()

            for event in self.device.read_loop():
                if not self.is_running:
                    break

                if event.type == ecodes.EV_KEY:
                    key_event = categorize(event)

                    if key_event.keystate == 1:
                        if key_event.keycode in ["KEY_PLAYCD", "KEY_PAUSECD"]:
                            self._trigger()

        except Exception as e:
            print(f"[Error] Headset disconnected: {e}")
        finally:
            try:
                self.device.ungrab()
            except:
                pass

    # =========================
    # Windows Listener
    # =========================
    def _listen_windows(self):
        if not WINDOWS_MEDIA:
            print("⚠️ Install pynput OR use AutoHotkey")
            return

        def on_press(key):
            try:
                if key == pynput_keyboard.Key.media_play_pause:
                    self._trigger()
            except:
                pass

        listener = pynput_keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()

        while self.is_running:
            time.sleep(0.1)

    # =========================
    # Trigger Assistant
    # =========================
    def _trigger(self):
        current_time = time.time()

        if current_time - self.last_trigger_time > 1.5:
            self.last_trigger_time = current_time

            print("🎤 Headset button pressed!")

            threading.Thread(
                target=self.on_command_trigger,
                daemon=True
            ).start()