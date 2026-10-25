"""Logging infrastructure tests; no application data or external services."""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta
from io import StringIO
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from django.conf import settings
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.test import AsyncClient, RequestFactory, SimpleTestCase, override_settings
from django.urls import path

from mysite.logging import JSONFormatter, MAX_MESSAGE_LENGTH, MAX_STACK_LENGTH
from mysite.middleware import RequestIDMiddleware
from mysite.request_context import bind_request_id, get_request_id


logger = logging.getLogger(__name__)


def logged_view(request):
    logger.info('Request work completed', extra={'event': 'test.completed'})
    return JsonResponse({'ok': True})


def failed_view(request):
    raise RuntimeError('private-exception-value')


async def async_logged_view(request):
    await asyncio.sleep(0)
    logger.info('Async request work completed')
    return JsonResponse({'ok': True})


urlpatterns = [
    path('logged/', logged_view),
    path('failed/', failed_view),
    path('async/', async_logged_view),
]


@contextmanager
def captured_console():
    """Capture the configured handler, including propagation and formatter."""
    handler = logging.getLogger().handlers[0]
    stream = StringIO()
    with patch.object(handler, 'stream', stream):
        yield stream


class JSONFormatterTests(SimpleTestCase):
    def setUp(self):
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(JSONFormatter())
        self.logger = logging.Logger('main.logging_test', level=logging.DEBUG)
        self.logger.addHandler(self.handler)

    def records(self):
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    def test_levels_schema_and_utc_timestamp(self):
        for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL):
            self.logger.log(level, 'Event %s', logging.getLevelName(level))
        records = self.records()
        self.assertEqual(len(records), 5)
        for record, level in zip(records, ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')):
            self.assertEqual(set(record), {'timestamp', 'level', 'logger', 'message'})
            self.assertTrue(all(isinstance(value, str) for value in record.values()))
            self.assertEqual(record['level'], level)
            self.assertEqual(record['logger'], 'main.logging_test')
            self.assertEqual(datetime.fromisoformat(record['timestamp']).utcoffset(), timedelta(0))

    def test_multiline_and_control_characters_are_one_json_line(self):
        message = 'Quoted "event"\nnext\rline\t\x1b[31m\u2028end'
        self.logger.warning(message)
        self.logger.info('Second event')
        self.assertEqual(len(self.stream.getvalue().splitlines()), 2)
        self.assertEqual(self.records()[0]['message'], message)

    def test_exception_type_and_frames_without_values_locals_or_source(self):
        private_local = 'private-local-secret'
        try:
            raise ValueError('private-exception-secret')
        except ValueError:
            self.logger.exception('Operation failed')
        record = self.records()[0]
        self.assertEqual(record['exception'], {'type': 'ValueError'})
        self.assertIn('test_exception_type_and_frames', record['stack_trace'])
        self.assertIn('ValueError', record['stack_trace'])
        self.assertNotIn(private_local, self.stream.getvalue())
        self.assertNotIn('private-exception-secret', self.stream.getvalue())
        self.assertNotIn('raise ValueError', record['stack_trace'])
        self.assertEqual(len(self.stream.getvalue().splitlines()), 1)

    def test_request_and_unapproved_extras_are_not_serialized(self):
        request = RequestFactory().post(
            '/activation/private-path-secret/?token=private-query-secret',
            data='private-body-secret', content_type='application/json',
            HTTP_AUTHORIZATION='Bearer private-header-secret',
            HTTP_COOKIE='sessionid=private-session-secret',
        )
        self.logger.info('Safe event', extra={
            'request': request, 'password': 'private-password-secret',
            'secret_key': 'private-key-secret', 'credentials': object(),
            'request_body': 'private-body-secret', 'token': 'private-token-secret',
        })
        record = self.records()[0]
        self.assertEqual(record['http_method'], 'POST')
        self.assertNotIn('private-', self.stream.getvalue())

    def test_django_errors_exclude_raw_messages_and_keep_status_and_route(self):
        request = RequestFactory().get('/private-path-secret/?token=private-query-secret')
        request.request_id = str(UUID(int=1))
        request.resolver_match = SimpleNamespace(route='resources/<int:pk>/')
        for name in ('django.request', 'django.security.DisallowedHost', 'django.server'):
            record = logging.LogRecord(name, logging.ERROR, __file__, 1, '%s', ('private-message-secret',), None)
            record.request = request
            record.status_code = 500
            data = json.loads(JSONFormatter().format(record))
            self.assertEqual(data['status_code'], 500)
            self.assertEqual(data['request_id'], request.request_id)
            self.assertEqual(data['route'], 'resources/<int:pk>/')
            self.assertNotIn('private-', json.dumps(data))

    def test_server_socket_is_excluded(self):
        record = logging.LogRecord('django.server', logging.ERROR, __file__, 1, '%s', ('private-url-secret',), None)
        record.request = object()
        record.status_code = 400
        data = json.loads(JSONFormatter().format(record))
        self.assertEqual(data['status_code'], 400)
        self.assertNotIn('request_id', data)
        self.assertNotIn('private-url-secret', data['message'])

    def test_context_is_typed_and_allowlisted(self):
        self.logger.info('Event', extra={
            'event': 'resource.indexed', 'resource_count': 3,
            'duration_ms': 12, 'status_code': 200, 'unknown': {'x': object()},
        })
        record = self.records()[0]
        self.assertEqual(record['event'], 'resource.indexed')
        self.assertEqual(record['resource_count'], 3)
        self.assertEqual(record['duration_ms'], 12.0)
        self.assertIs(type(record['duration_ms']), float)
        self.assertIs(type(record['status_code']), int)
        self.assertNotIn('unknown', record)

    def test_invalid_context_is_omitted(self):
        for duration in (float('nan'), float('inf'), '12', True, -1, 10**1000):
            self.logger.info('Event', extra={
                'event': object(), 'resource_count': True, 'duration_ms': duration,
                'status_code': '500', 'request_id': 'injected\nlog',
            })
        for record in self.records():
            self.assertEqual(set(record), {'timestamp', 'level', 'logger', 'message'})

    def test_untrusted_message_size_is_bounded(self):
        self.logger.warning('x' * 100000)
        self.assertEqual(len(self.records()[0]['message']), MAX_MESSAGE_LENGTH)

    def test_invalid_percent_format_does_not_break_logging(self):
        self.logger.info('%d', 'invalid number')
        self.assertEqual(self.records()[0]['message'], 'Log message could not be formatted')

    def test_external_request_id_must_be_bounded_and_safe(self):
        self.logger.info('Outside request', extra={'request_id': 'job-123'})
        self.assertEqual(self.records()[0]['request_id'], 'job-123')
        for value in ('x' * 65, '', 'a b', '\r\ninjected', object()):
            self.logger.info('Outside request', extra={'request_id': value})
        for record in self.records()[1:]:
            self.assertNotIn('request_id', record)

    def test_context_id_takes_precedence_over_log_extra(self):
        with bind_request_id('active-request'):
            self.logger.info('Inside request', extra={'request_id': 'spoofed'})
        self.assertEqual(self.records()[0]['request_id'], 'active-request')
        self.assertIsNone(get_request_id())


@override_settings(ROOT_URLCONF='mysite.tests', DEBUG=False, ALLOWED_HOSTS=['testserver'])
class RequestCorrelationTests(SimpleTestCase):
    def test_generated_id_on_response_and_scoped_log_ignores_client_header(self):
        with captured_console() as stream:
            response = self.client.get('/logged/', HTTP_X_REQUEST_ID='client-supplied-id')
        record = json.loads(stream.getvalue())
        request_id = response['X-Request-ID']
        self.assertEqual(UUID(request_id).version, 4)
        self.assertNotEqual(request_id, 'client-supplied-id')
        self.assertEqual(record['request_id'], request_id)
        self.assertEqual(response.json(), {'ok': True})
        self.assertIsNone(get_request_id())

    def test_sequential_requests_have_distinct_ids_and_no_context_leak(self):
        first = self.client.get('/logged/')
        second = self.client.get('/logged/')
        self.assertNotEqual(first['X-Request-ID'], second['X-Request-ID'])
        self.assertIsNone(get_request_id())
        with captured_console() as stream:
            logger.info('Outside request')
        self.assertNotIn('request_id', json.loads(stream.getvalue()))

    def test_404_remains_correlated_after_middleware_returns(self):
        with captured_console() as stream:
            response = self.client.get('/missing/private-path-secret/?token=private-query-secret')
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['level'], 'WARNING')
        self.assertEqual(records[0]['status_code'], 404)
        self.assertEqual(records[0]['request_id'], response['X-Request-ID'])
        self.assertNotIn('private-', stream.getvalue())

    def test_500_preserves_json_traceback_and_does_not_change_error_response(self):
        self.client.raise_request_exception = False
        with captured_console() as stream:
            response = self.client.get('/failed/')
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['level'], 'ERROR')
        self.assertEqual(records[0]['exception'], {'type': 'RuntimeError'})
        self.assertLessEqual(len(records[0]['stack_trace']), MAX_STACK_LENGTH)
        self.assertEqual(records[0]['request_id'], response['X-Request-ID'])
        self.assertNotIn('private-exception-value', stream.getvalue())
        self.assertNotIn(b'private-exception-value', response.content)

    def test_disallowed_host_remains_visible_without_untrusted_host(self):
        with captured_console() as stream:
            response = self.client.get('/logged/', HTTP_HOST='private-host-secret.invalid')
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['logger'], 'django.security.DisallowedHost')
        self.assertEqual(records[0]['request_id'], response['X-Request-ID'])
        self.assertNotIn('private-host-secret', stream.getvalue())

    def test_cors_preflight_has_id_and_header_is_exposed(self):
        response = self.client.options('/logged/',
            HTTP_ORIGIN='http://localhost:5173', HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(UUID(response['X-Request-ID']).version, 4)
        response = self.client.get('/logged/', HTTP_ORIGIN='http://localhost:5173')
        self.assertIn('X-Request-ID', response['Access-Control-Expose-Headers'])

    def test_exception_resets_context_for_direct_middleware_call(self):
        def raises(request):
            self.assertEqual(get_request_id(), request.request_id)
            raise RuntimeError('failed')
        with self.assertRaises(RuntimeError):
            RequestIDMiddleware(raises)(RequestFactory().get('/'))
        self.assertIsNone(get_request_id())

    async def test_async_client_uses_configured_middleware(self):
        with captured_console() as stream:
            response = await AsyncClient().get('/async/')
        self.assertEqual(json.loads(stream.getvalue())['request_id'], response['X-Request-ID'])
        self.assertIsNone(get_request_id())

    async def test_concurrent_async_requests_have_isolated_contexts(self):
        observed = {}
        async def view(request):
            before = get_request_id()
            await asyncio.sleep(0)
            observed[request.path] = (before, get_request_id(), request.request_id)
            return HttpResponse('ok')
        middleware = RequestIDMiddleware(view)
        await asyncio.gather(*(middleware(RequestFactory().get(f'/{i}/')) for i in range(10)))
        self.assertEqual(len({values[0] for values in observed.values()}), 10)
        for before, after, request_id in observed.values():
            self.assertEqual(before, request_id)
            self.assertEqual(after, request_id)
        self.assertIsNone(get_request_id())

    async def test_async_cancellation_restores_context(self):
        async def view(request):
            self.assertEqual(get_request_id(), request.request_id)
            raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await RequestIDMiddleware(view)(RequestFactory().get('/'))
        self.assertIsNone(get_request_id())

    def test_streaming_logs_are_correlated_without_leaking_between_chunks(self):
        def content():
            logger.info('Streaming chunk')
            yield b'first'
            logger.info('Streaming chunk')
            yield b'second'
        middleware = RequestIDMiddleware(lambda request: StreamingHttpResponse(content()))
        response = middleware(RequestFactory().get('/'))
        with captured_console() as stream:
            for chunk in response.streaming_content:
                self.assertIn(chunk, (b'first', b'second'))
                self.assertIsNone(get_request_id())
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record['request_id'] == response['X-Request-ID'] for record in records))
        self.assertIsNone(get_request_id())
        response.close()

    async def test_async_streaming_context_and_cleanup(self):
        async def content():
            logger.info('Async streaming chunk')
            yield b'first'
            logger.info('Async streaming chunk')
            yield b'second'
        async def view(request):
            return StreamingHttpResponse(content())
        response = await RequestIDMiddleware(view)(RequestFactory().get('/'))
        with captured_console() as stream:
            chunks = []
            async for chunk in response.streaming_content:
                chunks.append(chunk)
                self.assertIsNone(get_request_id())
        self.assertEqual(chunks, [b'first', b'second'])
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record['request_id'] == response['X-Request-ID'] for record in records))
        self.assertIsNone(get_request_id())
        response.close()

    def test_streaming_failure_restores_context(self):
        def content():
            yield b'first'
            raise RuntimeError('stream failed')
        response = RequestIDMiddleware(lambda request: StreamingHttpResponse(content()))(RequestFactory().get('/'))
        iterator = response.streaming_content
        self.assertEqual(next(iterator), b'first')
        with self.assertRaises(RuntimeError):
            next(iterator)
        self.assertIsNone(get_request_id())
        response.close()


class LoggingConfigurationTests(SimpleTestCase):
    def test_single_console_handler_and_no_django_duplicates(self):
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)
        self.assertIs(type(root.handlers[0]), logging.StreamHandler)
        self.assertIsInstance(root.handlers[0].formatter, JSONFormatter)
        for name in ('accounts', 'library', 'community', 'main', 'mysite',
                     'django', 'django.request', 'django.security', 'django.server'):
            configured = logging.getLogger(name)
            self.assertFalse(configured.disabled)
            self.assertEqual(configured.handlers, [])
            self.assertTrue(configured.propagate)

    def test_server_errors_are_visible_but_success_and_sql_debug_are_quiet(self):
        with captured_console() as stream:
            logging.getLogger('django.server').info('HTTP success', extra={'status_code': 200})
            logging.getLogger('django.db.backends').debug('private SQL parameters')
            logging.getLogger('django.request').warning('Request warning')
            logging.getLogger('django.server').error('Server failure', extra={'status_code': 500})
            logging.getLogger('other_package').error('Package failure')
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([record['logger'] for record in records], ['django.request', 'django.server', 'other_package'])
        self.assertNotIn('private SQL', stream.getvalue())

    def run_settings_process(self, debug, log_level=None):
        env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'mysite.settings',
               'SECRET_KEY': 'logging-tests-only', 'DEBUG': debug}
        env.pop('LOG_LEVEL', None)
        if log_level is not None:
            env['LOG_LEVEL'] = log_level
        code = (
            'import django, logging; django.setup(); '
            'from django.conf import settings; '
            'logging.getLogger("main.test").debug("Diagnostic event"); '
            'logging.getLogger("main.test").info("Significant event"); '
            'logging.getLogger("django.request").error("Request failure"); '
            'logging.getLogger("django.server").error("Server failure", extra={"status_code": 500})'
        )
        return subprocess.run([sys.executable, '-c', code], env=env,
                              cwd=Path(__file__).resolve().parent.parent,
                              text=True, capture_output=True, check=False)

    def test_development_and_production_configuration_load(self):
        for debug, expected in (('true', ['DEBUG', 'INFO', 'ERROR', 'ERROR']),
                                ('false', ['INFO', 'ERROR', 'ERROR'])):
            with self.subTest(debug=debug):
                result = self.run_settings_process(debug)
                self.assertEqual(result.returncode, 0, result.stderr)
                records = [json.loads(line) for line in result.stdout.splitlines()]
                self.assertEqual([record['level'] for record in records], expected)
                self.assertEqual(result.stderr, '')

    def test_app_override_cannot_suppress_django_errors(self):
        result = self.run_settings_process('false', 'CRITICAL')
        self.assertEqual(result.returncode, 0, result.stderr)
        records = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([record['logger'] for record in records], ['django.request', 'django.server'])

    def test_invalid_log_level_fails_with_clear_configuration_error(self):
        result = self.run_settings_process('false', 'invalid')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('LOG_LEVEL must be', result.stderr)

    def test_default_asgi_and_wsgi_entry_points_load(self):
        env = {**os.environ, 'SECRET_KEY': 'logging-tests-only', 'DEBUG': 'false', 'LOG_LEVEL': 'INFO'}
        env.pop('DJANGO_SETTINGS_MODULE', None)
        result = subprocess.run([
            sys.executable, '-c',
            'import mysite.asgi, mysite.wsgi; from django.conf import settings; '
            'assert settings.SETTINGS_MODULE == "mysite.settings"; '
            'assert callable(mysite.asgi.application) and callable(mysite.wsgi.application)',
        ], env=env, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
