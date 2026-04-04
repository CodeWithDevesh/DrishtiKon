WEAPON_CLASSES = {"pistol", "knife"}


def is_weapon(label: str) -> bool:
    return label.lower() in WEAPON_CLASSES


def draw_alert(frame, text: str = "WEAPON DETECTED"):
    import cv2

    cv2.putText(
        frame,
        text,
        (20, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 255),
        3,
    )
    return frame
