"""Directory-plugin entrypoint, imported in Hermes' per-profile namespace."""


def register(ctx):
    from .email_steward import register as register_plugin
    register_plugin(ctx)
