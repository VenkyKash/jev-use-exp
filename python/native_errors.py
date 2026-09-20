"""Structured diagnostics without dumping arbitrary exception/HTTP bodies."""


class DiagnosticError(ValueError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details


def error_details(error):
    children = getattr(error, "exceptions", None)
    if children is not None:
        return dict(error_type=type(error).__name__, causes=[error_details(child) for child in children])
    result = dict(error_type=type(error).__name__)
    if isinstance(error, DiagnosticError):
        result.update(code=error.code, details=error.details)
    else:
        status = getattr(error, "status", getattr(error, "status_code", None))
        if type(status) is int:
            result["http_status"] = status
        request_id = getattr(error, "request_id", None)
        if isinstance(request_id, str):
            result["request_id"] = request_id[:256]
    return result
