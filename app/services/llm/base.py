"""
LLM base service adapter.
Provides unified generation interface supporting 'mock' and 'gemini' providers with timeouts and error handling.
"""

from typing import Any, Dict, List
import google.generativeai as genai

from app.core.config import GEMINI_API_KEY


def _generate_gemini(
    model: str,
    messages: List[Dict[str, Any]],
    temp: float,
    max_tokens: int,
    images: list = None,
) -> str:
    """
    Calls Google Gemini API using google.generativeai with a 15-second timeout.
    Raises RuntimeError on failure.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured in environment.")

    genai.configure(api_key=GEMINI_API_KEY)

    system_instruction = None
    chat_contents = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_instruction = content
        elif role == "assistant":
            chat_contents.append({"role": "model", "parts": [content]})
        else:
            chat_contents.append({"role": "user", "parts": [content]})

    if not chat_contents:
        chat_contents = [{"role": "user", "parts": ["Hello"]}]

    clean_model = model or "gemini-2.5-flash"
    if clean_model.startswith("models/"):
        clean_model = clean_model.replace("models/", "", 1)
    if clean_model == "gemini-1.5-flash":
        clean_model = "gemini-2.5-flash"

    model_kwargs: Dict[str, Any] = {
        "model_name": clean_model,
        "generation_config": genai.types.GenerationConfig(
            temperature=float(temp) if temp is not None else 0.7,
            max_output_tokens=int(max_tokens) if max_tokens else 2048,
        ),
    }
    if system_instruction:
        model_kwargs["system_instruction"] = system_instruction

    try:
        gemini_model = genai.GenerativeModel(**model_kwargs)
        if images:
            # build content = [prompt_text] + image parts ({"mime_type": m, "data": d})
            user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
            prompt_text = user_msgs[-1] if user_msgs else "Please analyze this image."
            image_parts = [{"mime_type": img.get("mime_type"), "data": img.get("data")} for img in images]
            content = [prompt_text] + image_parts
            response = gemini_model.generate_content(
                content,
                request_options={"timeout": 15},
            )
        else:
            response = gemini_model.generate_content(
                chat_contents,
                request_options={"timeout": 15},
            )
        if response and response.text:
            return response.text.strip()
        return "No response generated from AI."
    except Exception as exc:
        raise RuntimeError(f"Gemini API generation failed: {exc}") from exc


def generate_response(
    provider: str,
    model: str,
    messages: List[Dict[str, Any]],
    temp: float,
    max_tokens: int,
    images: list = None,
) -> str:
    """
    Adapter interface to generate LLM completions.
    - provider == 'mock': Returns mock educational response.
    - provider == 'gemini': Calls Google Gemini with a 15s timeout.
    """
    if images is None:
        images = []

    prov = (provider or "mock").strip().lower()

    if prov == "mock":
        reply = "This is a mock response from BD Legal Guide AI. In production, this will connect to the configured LLM provider."
        if images:
            reply += f" [{len(images)} image attachment(s) received and would be analyzed by Gemini vision in production.]"
        return reply

    if prov == "gemini":
        return _generate_gemini(model, messages, temp, max_tokens, images=images)

    # If any other provider is passed, raise a clear exception or fallback
    raise ValueError(f"Unsupported LLM provider: '{provider}'. Supported providers are 'mock' and 'gemini'.")
