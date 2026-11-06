"""The exact v1 REST contract; all mutations call the same owner service as chat."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .errors import Error, invalid
from .security import desktop_access


def create_router(service_factory):
    router = APIRouter()

    async def call(request, operation, *, mutation=False, status=200):
        try:
            service = service_factory()
            access = desktop_access(service.settings, request)
            payload = None
            if mutation:
                raw = bytearray()
                async for chunk in request.stream():
                    raw.extend(chunk)
                    if len(raw) > 100000:
                        raise invalid("JSON request exceeds limit")
                try:
                    import json
                    payload = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise invalid("Invalid JSON") from None
                if not isinstance(payload, dict):
                    raise invalid("JSON body must be an object")
            # DB/network work never holds the gateway event loop.
            import asyncio
            result = await asyncio.to_thread(operation, service, access, payload)
            return JSONResponse(result, status_code=status)
        except Error as exc:
            return JSONResponse(exc.body, status_code=exc.status)
        except Exception:
            return JSONResponse({"error": {"code": "service_unavailable", "message": "Email Steward is unavailable; no sensitive error detail is exposed."}}, status_code=503)

    @router.get("/mailboxes")
    async def mailboxes(request: Request):
        return await call(request, lambda s, a, p: {"mailboxes": s.mailboxes(a)})

    @router.get("/rules")
    async def rules(request: Request):
        return await call(request, lambda s, a, p: {"rules": s.rules(a)})

    @router.post("/rules", status_code=201)
    async def create(request: Request):
        return await call(request, lambda s, a, p: {"rule": s.save_rule(a, p)}, mutation=True, status=201)

    @router.post("/rules/preview")
    async def preview(request: Request):
        return await call(request, lambda s, a, p: s.preview(a, p), mutation=True)

    @router.put("/rules/{ident}")
    async def update(ident: str, request: Request):
        return await call(request, lambda s, a, p: {"rule": s.save_rule(a, p, ident)}, mutation=True)

    @router.post("/rules/{ident}/toggle")
    async def toggle(ident: str, request: Request):
        return await call(request, lambda s, a, p: {"rule": s.toggle_rule(a, ident, p)}, mutation=True)

    @router.get("/packs")
    async def packs(request: Request):
        return await call(request, lambda s, a, p: {"packs": s.packs(a)})

    @router.post("/packs/{ident}/enable")
    async def enable(ident: str, request: Request):
        return await call(request, lambda s, a, p: {"rules": s.enable_pack(a, ident, p)}, mutation=True)

    @router.get("/items")
    async def items(request: Request):
        return await call(request, lambda s, a, p: {"items": s.items(a)})

    @router.post("/items/{reference}/correct")
    async def correct(reference: str, request: Request):
        return await call(request, lambda s, a, p: s.correct(a, reference, p), mutation=True)

    return router
