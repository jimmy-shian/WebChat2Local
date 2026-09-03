"""
Gemini Web Model Catalog & Routing Specifications.
Modeled after codex-chatgpt-web model-catalog.ts and chatgpt-web-models.ts.
Provides context limits, tokenizer budgets, reasoning support, and slug mapping.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class GeminiWebModelRoute(BaseModel):
    id: str
    slug: str
    display_name: str
    backend_mode: str  # "flash", "pro", "thinking", "ultra", "auto"
    description: str
    context_window: int = 32_768  # 32K token safe limit for Gemini Web browser transport
    max_output_tokens: int = 8_192
    compaction_reserve_ratio: float = 0.10
    supports_thinking: bool = True
    supports_tools: bool = True
    supports_vision: bool = True
    is_default: bool = False


# Supported Gemini Web model definitions
AVAILABLE_GEMINI_WEB_ROUTES: List[GeminiWebModelRoute] = [
    GeminiWebModelRoute(
        id="gemini-web/flash",
        slug="gemini-web/flash",
        display_name="Gemini Web - 2.5 Flash",
        backend_mode="flash",
        description="High-speed multimodal Gemini 2.5 Flash model with 32K context window and thinking capability.",
        context_window=32_768,
        max_output_tokens=8_192,
        supports_thinking=True,
        is_default=False,
    ),
    GeminiWebModelRoute(
        id="gemini-web/pro",
        slug="gemini-web/pro",
        display_name="Gemini Web - 2.5 Pro",
        backend_mode="pro",
        description="Flagship Gemini 2.5 Pro reasoning model with 32K context window, deep coding intelligence, and rich reasoning.",
        context_window=32_768,
        max_output_tokens=8_192,
        supports_thinking=True,
        is_default=True,
    ),
    GeminiWebModelRoute(
        id="gemini-web/flash-thinking",
        slug="gemini-web/flash-thinking",
        display_name="Gemini Web - Flash Thinking",
        backend_mode="thinking",
        description="Gemini Flash Thinking experimental model with real-time reasoning_content deltas.",
        context_window=32_768,
        max_output_tokens=8_192,
        supports_thinking=True,
        is_default=False,
    ),
    GeminiWebModelRoute(
        id="gemini-web/ultra",
        slug="gemini-web/ultra",
        display_name="Gemini Web - Advanced Ultra",
        backend_mode="ultra",
        description="Gemini Advanced / Ultra tier for complex tasks.",
        context_window=32_768,
        max_output_tokens=8_192,
        supports_thinking=True,
        is_default=False,
    ),
    GeminiWebModelRoute(
        id="gemini-web/auto",
        slug="gemini-web/auto",
        display_name="Gemini Web - Auto",
        backend_mode="auto",
        description="Automatically routes to the best available Gemini Web model on current page.",
        context_window=1_048_576,
        max_output_tokens=32_768,
        supports_thinking=True,
        is_default=False,
    ),
]

# Alias map for standard client interoperability (Cline, Kilo, Cursor, RooCode)
MODEL_ALIAS_MAP: Dict[str, str] = {
    "gemini-2.5-pro": "gemini-web/pro",
    "gemini-2.0-pro": "gemini-web/pro",
    "gemini-1.5-pro": "gemini-web/pro",
    "gemini-pro": "gemini-web/pro",
    "gemini-2.5-flash": "gemini-web/flash",
    "gemini-2.0-flash": "gemini-web/flash",
    "gemini-1.5-flash": "gemini-web/flash",
    "gemini-flash": "gemini-web/flash",
    "gemini-web/thinking": "gemini-web/flash-thinking",
    "gemini-thinking": "gemini-web/flash-thinking",
    "gemini-2.5-flash-thinking": "gemini-web/flash-thinking",
    "gpt-4o": "gemini-web/pro",
    "gpt-4o-mini": "gemini-web/flash",
    "claude-3-5-sonnet": "gemini-web/pro",
}


def resolve_model_route(model_id: Optional[str]) -> GeminiWebModelRoute:
    """
    Resolves any requested model string (including aliases) to a canonical GeminiWebModelRoute.
    Defaults to gemini-web/pro if unknown.
    """
    if not model_id:
        return next(r for r in AVAILABLE_GEMINI_WEB_ROUTES if r.is_default)

    norm_id = model_id.strip().lower()
    # Check alias map
    if norm_id in MODEL_ALIAS_MAP:
        norm_id = MODEL_ALIAS_MAP[norm_id]

    for route in AVAILABLE_GEMINI_WEB_ROUTES:
        if route.id == norm_id or route.slug == norm_id or route.backend_mode == norm_id:
            return route

    # Return default pro route
    return next(r for r in AVAILABLE_GEMINI_WEB_ROUTES if r.is_default)


def get_openai_model_catalog() -> List[Dict[str, Any]]:
    """
    Formats the model catalog into the standard OpenAI /v1/models response structure.
    """
    catalog = []
    for route in AVAILABLE_GEMINI_WEB_ROUTES:
        catalog.append({
            "id": route.id,
            "object": "model",
            "created": 1740000000,
            "owned_by": "gemini-web",
            "permission": [],
            "root": route.id,
            "parent": None,
            "display_name": route.display_name,
            "description": route.description,
            "context_window": route.context_window,
            "max_output_tokens": route.max_output_tokens,
            "supports_thinking": route.supports_thinking,
            "supports_tools": route.supports_tools,
            "pricing": {"prompt": "0", "completion": "0"},
        })

    # Add standard aliases
    for alias, target in MODEL_ALIAS_MAP.items():
        if not any(m["id"] == alias for m in catalog):
            target_route = resolve_model_route(target)
            catalog.append({
                "id": alias,
                "object": "model",
                "created": 1740000000,
                "owned_by": "gemini-web",
                "permission": [],
                "root": target_route.id,
                "parent": target_route.id,
                "display_name": f"{alias} (-> {target_route.display_name})",
                "description": f"Alias routing to {target_route.id}",
                "context_window": target_route.context_window,
                "max_output_tokens": target_route.max_output_tokens,
                "supports_thinking": target_route.supports_thinking,
                "supports_tools": target_route.supports_tools,
                "pricing": {"prompt": "0", "completion": "0"},
            })

    return catalog
