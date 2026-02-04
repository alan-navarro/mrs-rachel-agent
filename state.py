# state.py
user_sessions = {}

def get_user(phone):
    if phone not in user_sessions:
        user_sessions[phone] = {
            "lang": None,
            "step": "LANG"
        }
    return user_sessions[phone]

def reset_user(phone):
    user_sessions.pop(phone, None)
