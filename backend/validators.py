import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$|^[^@\s]+@[^@\s]+$")


def check_name(v):
    v = (v or "").strip()
    if len(v) < 2 or len(v) > 80:
        return "Name must be 2-80 characters."
    return None


def check_email(v):
    v = (v or "").strip()
    if not EMAIL_RE.match(v) or len(v) > 120:
        return "Please enter a valid email address."
    return None


def check_password(v):
    v = v or ""
    if len(v) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
        return "Password must contain at least one letter and one number."
    return None


def check_pin(v):
    v = (v or "").strip()
    if not re.fullmatch(r"\d{4,6}", v):
        return "PIN must be 4 to 6 digits."
    if len(set(v)) == 1 or v in ("1234", "123456", "0000", "1111"):
        return "Please choose a less predictable PIN."
    return None
