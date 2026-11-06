"""Public errors carry safe, bounded messages, never provider exception strings."""
class Error(Exception):
    def __init__(self, code, message, status=422, *, fields=None, current=None):
        super().__init__(message)
        self.status = status
        self.body = {"error": {"code": code, "message": message}}
        if fields is not None:
            self.body["error"]["fields"] = fields
        if current is not None:
            self.body["error"]["current"] = current


def invalid(message, **fields):
    return Error("validation_error", message, fields=fields or None)
