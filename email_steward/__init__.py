"""Email Steward native plugin package."""
__version__ = "0.1.0"


def register(ctx):
    from .plugin import register as register_plugin
    register_plugin(ctx)
