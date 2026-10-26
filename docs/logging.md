# Backend logging

Logging is configured once through `LOGGING` in `mysite/settings.py`, using
Python's standard `logging` framework and `mysite.logging.JSONFormatter`.
No dependencies, storage services, or file handlers are added.

## Configuration

The only handler is `console`, a `logging.StreamHandler` writing to `sys.stdout`.
It has no debug-only filter or severity threshold. Application and Django
loggers propagate to this handler, with no handlers of their own, so events are
formatted once. Django's default plain-text server and admin-email handlers are
replaced by console output. Existing third-party loggers remain enabled.

Settings continue to use `python-dotenv`: process environment values take
precedence over the ignored `.env` file.

| Setting | Behavior |
| --- | --- |
| `DEBUG` | Defaults to `true`, preserving development behavior. `1`, `true`, `yes`, and `on`, ignoring case and surrounding whitespace, enable it; other values disable it. Set `false` in production. |
| `LOG_LEVEL` | Application threshold: `DEBUG` when debug is enabled, otherwise `INFO`. Accepts `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`, ignoring case/whitespace. Invalid values fail startup with a clear error. |
| Root logger | Uses `LOG_LEVEL`, with a minimum threshold of `INFO` to avoid enabling third-party debug output when application debugging is enabled. |
| Application namespaces | `accounts`, `library`, `community`, `main`, and `mysite` use `LOG_LEVEL`. |
| `django` | `INFO`, preserving framework diagnostics. |
| `django.request`, `django.security`, `django.server` | `WARNING`. HTTP and server errors remain visible in development and production, even if the application threshold is `CRITICAL`. Routine development-server successful-request logs are suppressed. |
| `django.db.backends` | `WARNING`, excluding debug SQL and parameters that could contain credentials or personal information. |

Explicit child logger levels control propagated records; the root's level does
not filter events already accepted by Django or application loggers. The shared
handler accepts those records. There is no additional successful-request access
logging middleware.

## JSON schema

Each event is one valid JSON object followed by a newline. Embedded newlines,
control characters, and Unicode are JSON-escaped. Optional fields are omitted
when absent, invalid, or inapplicable; they are never filled with placeholder
values or `null`.

| Field | JSON type | Policy |
| --- | --- | --- |
| `timestamp` | string | Always present; event time in ISO 8601 UTC with milliseconds and `+00:00`. |
| `level` | string | Always present; standard uppercase severity. |
| `logger` | string | Always present; module/logger name, limited to 256 characters. |
| `message` | string | Always present; formatted message, limited to 4,096 characters. |
| `request_id` | string | Included from the attached request, active request context, or an explicit log extra, in that priority order. Must be 1–64 ASCII characters, start with an alphanumeric character, and contain only alphanumeric characters, `.`, `_`, or `-`. |
| `exception` | object | Included with exception information; contains `type` as a string. Raw exception values are intentionally excluded. |
| `stack_trace` | string | Included when an exception has a traceback; newest 32 frames with filenames, line numbers, and function names, limited to 16,384 characters. No source lines, locals, exception values, notes, or chained exceptions are rendered. |
| `status_code` | integer | Included when supplied by Django or `extra`; accepts 100–599. |
| `http_method` | string | Included from an attached request; 1–16 uppercase ASCII letters. |
| `route` | string | Included from Django's resolved route template, limited to 512 characters. Contains parameter placeholders rather than actual URL values. Omitted for unresolved routes. |
| `event` | string | Optional `extra` field for a stable event name: up to 128 lowercase ASCII letters, digits, `_`, or `.`, beginning with a letter. |
| `resource_count` | integer | Optional `extra` field; nonnegative integer up to `2**63 - 1`. |
| `duration_ms` | number | Optional `extra` field; finite nonnegative number up to `2**63 - 1`, consistently emitted as a float. |

Other extras are excluded rather than serialized with `str()` or arbitrary object
conversion. Malformed percent-formatting produces a safe fallback message.
Limits are character limits before JSON escaping, not a byte quota for collectors.

Django request error messages with an attached request are normalized to the
standard HTTP reason phrase. Security events and development-server messages use
fixed descriptions. This excludes raw paths, query strings, hostnames, request
lines, and exception values while retaining severity, logger, status, correlation,
resolved route, and exception frames where available.

Example emitted by the configured handler and request middleware in this
workspace, using a diagnostic event with a sample resource count:

```json
{"timestamp":"2026-10-25T19:19:03.188+00:00","level":"INFO","logger":"main.logging_example","message":"Resource indexing completed","request_id":"dd0b3552-3509-4632-9719-9ae1e9a6b35b","event":"resources.indexed","resource_count":3}
```

## Request correlation

`mysite.middleware.RequestIDMiddleware` runs first, including before CORS
preflight handling and middleware that can return early. It assigns a fresh
UUID4 to every incoming request. Client-supplied `X-Request-ID` headers are
ignored, so arbitrary, oversized, or forged values are never accepted or echoed.

Application code can use `request.request_id`, or call
`mysite.request_context.get_request_id()` when no request object is available.
The latter returns `None` outside a request. A `ContextVar` isolates concurrent
async requests and is restored on normal completion, exceptions, and cancellation.
Both synchronous and asynchronous streaming iterators bind correlation while
producing each chunk and restore the caller's context before yielding it.

The response includes `X-Request-ID`. `CORS_EXPOSE_HEADERS` exposes that response
header to the separate frontend. Request IDs identify a request, not a user or
permission. Existing endpoint bodies, status codes, and exception handling are
unchanged.

Django may log a returned 4xx response after middleware completes. The formatter
uses its attached request's ID in that case. Development-server socket logs
outside request processing do not carry an HTTP request object; their request ID
is omitted. No connection-to-request mapping or distributed tracing is added.

Background work must carry correlation explicitly when needed, for example
`extra={'request_id': request.request_id}`. Newly spawned async tasks inherit
context; avoid detached tasks that inadvertently retain a completed request's
context. Correlation is established for the request pipeline and stream
production, not arbitrary later response cleanup callbacks.

## Development conventions

Use a module-level logger:

```python
import logging

logger = logging.getLogger(__name__)

logger.info('Resource indexing completed', extra={
    'event': 'resources.indexed',
    'resource_count': indexed_count,
})

try:
    perform_operation()
except ExpectedOperationError:
    logger.exception('Resource operation failed')
```

| Level/method | Use |
| --- | --- |
| `DEBUG` | Development diagnostics. |
| `INFO` | Significant application events. |
| `WARNING` | Unexpected conditions where operation can continue. |
| `ERROR` | Failure preventing an operation from completing. |
| `CRITICAL` | Failure requiring immediate attention. |
| `logger.exception()` | Inside an exception handler when exception type and traceback frames help diagnosis. |

Use descriptive, safe messages and approved diagnostic extras. Never include
passwords, JWTs, secret keys, credentials, authorization headers, session
contents, request bodies, or sensitive personal information. Do not interpolate
raw exceptions, request objects, URLs, or external payloads into messages.
Formatter exclusions do not redact secrets deliberately placed in ordinary
application messages or approved extras; developers remain responsible for their
content. `stack_info` and preformatted `exc_text` are not emitted.

Existing Drive prints now use module logging. Crawl/search failures use fixed
messages with `logger.exception()`, avoiding raw external error payloads. Drive
listing diagnostics report a count rather than file names or identifiers.

## Verification and deployment

Inspected Python 3.13.14, Django 6.0.3, pinned dependencies, active settings,
environment variable names, WSGI/ASGI entry points, `wiz.sh`, root routing,
existing middleware, logger/print usage, exception handling, and existing Django
test settings. The ASGI entry point referenced a nonexistent settings module;
it now defaults to `mysite.settings`, matching WSGI and `manage.py`.

Run only the logging infrastructure tests, using the existing isolated test
settings to avoid application data and Google Drive startup:

```text
uv run python manage.py test mysite --settings=accounts.tests.settings
uv run python manage.py check
git diff --check
```

Tests cover JSON/schema/escaping, exception exclusions, safe extras, generated
and isolated request IDs, sync/async/streaming behavior, CORS preflight, real
Django 404/500/security logs, handler propagation, environment thresholds,
configuration validation, and WSGI/ASGI startup. No application test suite is
required for this logging task. System checks and management-command progress
messages are command output and may remain plain text; they are not log records.
Python runtime warnings also remain warnings rather than logging records. The
entry-point startup check observed an existing WhiteNoise warning about the
missing collected `staticfiles` directory; startup still succeeded.

| Changed file | Reason |
| --- | --- |
| `mysite/settings.py` | Central console configuration, environment thresholds, middleware registration, and CORS exposure. |
| `mysite/logging.py` | JSON schema, bounded fields, safe request/framework formatting, and exception frames. |
| `mysite/request_context.py` | Shared context-local correlation and restoration. |
| `mysite/middleware.py` | UUID generation, response header, and sync/async/streaming correlation. |
| `mysite/asgi.py` | Correct the nonexistent default settings module so ASGI loads logging. |
| `main/drive_api.py` | Replace existing prints and sensitive raw error messages with module logging. |
| `mysite/tests.py` | Focused logging infrastructure regression tests. |
| `README.md`, `docs/logging.md` | Developer entry point, schema, conventions, and verification/deployment guidance. |

The pre-existing `.gitignore` modification is preserved. No models, migrations,
API endpoint implementations, or dependency pins changed.

Verification on 2026-10-25: all 31 focused logging tests passed; the default
Django system check reported no issues; Git diff whitespace validation passed.
An initial startup-test assertion incorrectly treated the existing WhiteNoise
warning as a failure; the assertion now verifies successful entry-point loading.

No hosting-platform configuration was found. Verify stdout collection,
JSON parsing, retention, indexing, and any process-server or reverse-proxy access
logs in the actual deployment. Those servers configure their own output outside
Django's `LOGGING`. This task does not add collectors or claim hosting support.
Production must provide its existing required configuration and set `DEBUG=false`.
