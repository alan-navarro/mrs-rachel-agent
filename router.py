# router.py
from responses import RESPONSES

def route_message(message, state):

    step = state["step"]

    # --- LANG SELECTION ---
    if step == "LANG":
        if message == "1":
            state["lang"] = "es"
        elif message == "2":
            state["lang"] = "en"
        elif message == "3":
            state["lang"] = "fr"
        else:
            return "LANG"

        state["step"] = "MENU"
        return "MENU"

    # --- MAIN MENU ---
    if step == "MENU":
        if message == "1":
            state["step"] = "END"
            return "TRANSFER"
        if message == "2":
            state["step"] = "END"
            return "RESCHEDULE"
        return "INVALID"

    return "END"
