"""Owner and registration admission before a Vision operation creates images."""

import asyncio
import time

import httpx
from fastapi import HTTPException

from ..chatgpt_store import ChatGPTError
from ..model_settings import provider_for_model
from .common import MODEL_NOT_OFFERED_DETAIL, _model_offered_to


def chatgpt_vision_error(error: ChatGPTError) -> HTTPException:
    status = 503 if error.failure == "transport_unavailable" else 403
    return HTTPException(status_code=status, detail={"code": error.code, "action": error.action})


def prepare_vision_settings(actor: dict, model: str, settings: dict) -> dict:
    provider, model_id = provider_for_model(model, stage="stage1", settings=settings)
    if provider != "chatgpt":
        if not _model_offered_to(actor, model, stage="stage1", purpose="vision", settings=settings, operation="vision"):
            raise HTTPException(status_code=403, detail=MODEL_NOT_OFFERED_DETAIL)
        return settings
    from ..chatgpt_provider import catalog, pin
    try:
        profile_id, generation = pin(actor["id"])
        models = asyncio.run(catalog(actor["id"], profile_id, generation, time.monotonic() + 15))
        if not any(entry["id"] == model_id and entry["enabled"] and "vision" in entry["purposes"] for entry in models):
            raise ChatGPTError("chatgpt_model_not_offered")
        return {**settings, "chatgpt_owner_id": actor["id"], "chatgpt_profile_id": profile_id,
                "chatgpt_generation": generation}
    except ChatGPTError as error:
        raise chatgpt_vision_error(error) from None
    except (httpx.HTTPError, TimeoutError):
        raise chatgpt_vision_error(ChatGPTError("chatgpt_transport_unavailable")) from None
    except (ValueError, KeyError, TypeError):
        raise chatgpt_vision_error(ChatGPTError("chatgpt_response_invalid")) from None
