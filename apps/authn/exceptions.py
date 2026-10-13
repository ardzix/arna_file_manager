import uuid
from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler as drf_exception_handler


def detail(value):
    if isinstance(value, dict):
        return ' '.join(f'{key}: {detail(message)}' for key, message in value.items())
    if isinstance(value, list):
        return ' '.join(detail(message) for message in value)
    return str(value)


def exception_handler(exc, context):
    if isinstance(exc, ModelValidationError):
        exc = ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)
    response = drf_exception_handler(exc, context)
    if response is not None:
        response.data = {'error': getattr(exc, 'default_code', 'invalid_request'),
                         'detail': detail(getattr(exc, 'detail', exc)), 'request_id': str(uuid.uuid4())}
    return response
