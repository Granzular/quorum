"""Assign server-generated correlation IDs without logging request contents."""

from uuid import uuid4

from asgiref.sync import iscoroutinefunction
from django.utils.decorators import sync_and_async_middleware

from mysite.request_context import bind_request_id


def _prepare_response(response, request_id):
    response['X-Request-ID'] = request_id
    if response.streaming:
        content = response.streaming_content
        if response.is_async:
            async def stream():
                while True:
                    with bind_request_id(request_id):
                        try:
                            chunk = await anext(content)
                        except StopAsyncIteration:
                            return
                    yield chunk
        else:
            def stream():
                while True:
                    with bind_request_id(request_id):
                        try:
                            chunk = next(content)
                        except StopIteration:
                            return
                    yield chunk
        response.streaming_content = stream()
    return response


@sync_and_async_middleware
def RequestIDMiddleware(get_response):
    """Correlate sync/async requests and streaming logs with a fresh UUID4.

    Incoming X-Request-ID headers are deliberately ignored: correlation IDs
    identify this backend's request and never establish identity or privilege.
    """
    if iscoroutinefunction(get_response):
        async def middleware(request):
            request.request_id = str(uuid4())
            with bind_request_id(request.request_id):
                response = await get_response(request)
            return _prepare_response(response, request.request_id)
    else:
        def middleware(request):
            request.request_id = str(uuid4())
            with bind_request_id(request.request_id):
                response = get_response(request)
            return _prepare_response(response, request.request_id)
    return middleware
