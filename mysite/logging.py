"""Bounded JSON console records with an explicit diagnostic field allowlist."""

from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
import json
import logging
import math
import re
import traceback

from mysite.request_context import get_request_id


MAX_MESSAGE_LENGTH = 4096
MAX_STACK_LENGTH = 16384
REQUEST_ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z', re.ASCII)


def _bounded(value, limit):
    return value if len(value) <= limit else value[:limit - 3] + '...'


def _valid_request_id(value):
    return isinstance(value, str) and REQUEST_ID_PATTERN.fullmatch(value) is not None


class JSONFormatter(logging.Formatter):
    """Emit one JSON object; omit fields without applicable, safe values.

    Request objects, arbitrary extras, exception values, source lines and locals
    are excluded because they may contain credentials or personal information.
    """

    def format(self, record):
        request = getattr(record, 'request', None)
        status_code = getattr(record, 'status_code', None)
        if type(status_code) is not int or not 100 <= status_code <= 599:
            status_code = None

        if record.name == 'django.server':
            # Development-server messages include raw URLs and sometimes input.
            message = 'Development server HTTP response' if status_code else 'Development server error'
        elif record.name.startswith('django.security'):
            message = 'HTTP security check failed'
        elif record.name == 'django.request' and request is not None:
            message = HTTPStatus(status_code).phrase if status_code in HTTPStatus else 'HTTP request error'
        else:
            try:
                message = record.getMessage()
            except Exception:
                message = 'Log message could not be formatted'

        data = {
            'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'logger': _bounded(record.name, 256),
            'message': _bounded(message, MAX_MESSAGE_LENGTH),
        }
        request_id = (
            getattr(request, 'request_id', None)
            or get_request_id()
            or getattr(record, 'request_id', None)
        )
        if _valid_request_id(request_id):
            data['request_id'] = request_id
        if status_code is not None:
            data['status_code'] = status_code
        method = getattr(request, 'method', None)
        if isinstance(method, str) and re.fullmatch(r'[A-Z]{1,16}', method, re.ASCII):
            data['http_method'] = method
        route = getattr(getattr(request, 'resolver_match', None), 'route', None)
        if isinstance(route, str):
            data['route'] = _bounded(route, 512)
        event = getattr(record, 'event', None)
        if isinstance(event, str) and re.fullmatch(r'[a-z][a-z0-9_.]{0,127}', event, re.ASCII):
            data['event'] = event
        resource_count = getattr(record, 'resource_count', None)
        if type(resource_count) is int and 0 <= resource_count <= 2**63 - 1:
            data['resource_count'] = resource_count
        duration = getattr(record, 'duration_ms', None)
        if type(duration) in (int, float) and 0 <= duration <= 2**63 - 1 and math.isfinite(duration):
            data['duration_ms'] = float(duration)

        if record.exc_info and record.exc_info[0] is not None:
            exception_type, _, tb = record.exc_info
            name = _bounded(exception_type.__name__, 128)
            data['exception'] = {'type': name}
            # Walk frames without fetching source or rendering exception values.
            frames = deque(traceback.walk_tb(tb), maxlen=32) if tb else []
            lines = ['Traceback (most recent call last):'] if frames else []
            for frame, lineno in frames:
                code = frame.f_code
                lines.append(f'  File "{code.co_filename}", line {lineno}, in {code.co_name}')
            if frames:
                lines.append(name)
                data['stack_trace'] = _bounded('\n'.join(lines), MAX_STACK_LENGTH)

        return json.dumps(data, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
