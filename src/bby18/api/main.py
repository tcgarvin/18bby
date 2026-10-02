"""The ASGI entry point, configured from the environment. See ``settings_from_env``."""

from bby18.api.app import app_from_settings, settings_from_env

app = app_from_settings(settings_from_env())
