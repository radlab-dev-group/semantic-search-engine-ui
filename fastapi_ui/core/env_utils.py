import os


def bool_env_value(env_name: str) -> bool:
    env_value = os.getenv(env_name, "false").lower()
    if env_value in ["true", "1", "t", "y", "yes", "tak"]:
        return True
    return False
