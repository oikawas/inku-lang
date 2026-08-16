"""The gzip layer, with one difference: a streamed body leaves as it is written.

Starlette's own responder writes each chunk into a ``GzipFile`` and hands on
whatever the compressor happens to have produced.  zlib holds its output back
until it has enough to be worth emitting, so a body written in small pieces
produces nothing until the file is closed at the end of the response.  For a
whole response that is right -- it is what makes the compression good -- but
``/api/paint/stream`` writes a few hundred bytes per event *while it works*,
and the browser reads them as they arrive to say which stage is running.  Under
the stock responder those events reached the client only once the drawing was
finished: measured 2026-08-16 with five events, the bytes leaving per event
were 10 / 0 / 0 / 0 / 117, the ten being the gzip header alone.

``Z_SYNC_FLUSH`` after each chunk ends the current deflate block so the bytes
so far can be read, and leaves the compressor open for the rest.  It costs a
few bytes per flush and keeps the dictionary, so the final size is essentially
unchanged; the last chunk closes the file as before.
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware, GZipResponder, IdentityResponder
from starlette.types import ASGIApp, Receive, Scope, Send


class _FlushingGZipResponder(GZipResponder):
    """Starlette's responder, flushing what it has after every chunk."""

    def apply_compression(self, body: bytes, *, more_body: bool) -> bytes:
        self.gzip_file.write(body)
        if more_body:
            # GzipFile.flush defaults to Z_SYNC_FLUSH: it does not finish the
            # stream, so the file stays writable for the chunks still to come.
            self.gzip_file.flush()
        else:
            self.gzip_file.close()

        body = self.gzip_buffer.getvalue()
        self.gzip_buffer.seek(0)
        self.gzip_buffer.truncate()

        return body


class FlushingGZipMiddleware(GZipMiddleware):
    """GZipMiddleware, answering with the responder above.

    The identity path -- a client that did not ask for gzip -- is Starlette's
    own and is left alone: it compresses nothing, so it has nothing to hold.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        responder: ASGIApp
        if "gzip" in headers.get("Accept-Encoding", ""):
            responder = _FlushingGZipResponder(
                self.app, self.minimum_size, compresslevel=self.compresslevel
            )
        else:
            responder = IdentityResponder(self.app, self.minimum_size)

        await responder(scope, receive, send)
