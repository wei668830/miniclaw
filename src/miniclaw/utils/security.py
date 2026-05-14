
def mask_password(password: str) -> str:
    """Mask a password by replacing middle characters with asterisks."""
    if len(password) <= 6:
        return "*" * len(password)
    return password[:3] + "*" * (len(password) - 6) + password[-3:]