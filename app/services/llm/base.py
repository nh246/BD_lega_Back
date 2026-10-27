"""
LLM base service adapter.
Provides unified generation interface supporting 'mock' and 'gemini' providers with timeouts and error handling.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple
import google.generativeai as genai


def resolve_provider_credential(provider: str) -> Tuple[Optional[str], Optional[str], str]:
    """
    Resolves API key and base_url for provider:
    1. Checks ProviderCredential table in database (DB-first).
    2. Falls back to environment variables.
    Returns (api_key, base_url, source) where source is 'db', 'env', or 'none'.
    """
    prov = (provider or "").strip().lower()
    if prov == "mock":
        return ("mock-key", None, "mock")

    db_key = None
    db_base_url = None

    try:
        from app.core.database import SessionLocal
        from app.models import ProviderCredential
        db = SessionLocal()
        try:
            row = db.query(ProviderCredential).filter(ProviderCredential.provider == prov).first()
            if row:
                if row.api_key and row.api_key.strip():
                    db_key = row.api_key.strip()
                if row.base_url and row.base_url.strip():
                    db_base_url = row.base_url.strip()
        finally:
            db.close()
    except Exception:
        pass

    if db_key:
        return (db_key, db_base_url, "db")

    # Fallback to environment variables
    from app.core.config import GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY
    env_map = {
        "gemini": GEMINI_API_KEY,
        "openai": OPENAI_API_KEY,
        "anthropic": ANTHROPIC_API_KEY,
        "openrouter": OPENROUTER_API_KEY,
    }
    env_key = env_map.get(prov, "")
    if env_key and env_key.strip():
        return (env_key.strip(), db_base_url, "env")

    return (None, db_base_url, "none")


def _generate_gemini(
    model: str,
    messages: List[Dict[str, Any]],
    temp: float,
    max_tokens: int,
    images: list = None,
) -> str:
    """
    Calls Google Gemini API using resolved credentials with timeout and error handling.
    Raises RuntimeError on failure.
    """
    api_key, base_url, source = resolve_provider_credential("gemini")
    if not api_key:
        raise RuntimeError("GEMINI API key is not configured in database credentials or environment variables.")

    genai_kwargs: Dict[str, Any] = {"api_key": api_key}
    if base_url:
        genai_kwargs["client_options"] = {"api_endpoint": base_url}
    genai.configure(**genai_kwargs)

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
            user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
            prompt_text = user_msgs[-1] if user_msgs else "Please analyze this image."
            image_parts = [{"mime_type": img.get("mime_type"), "data": img.get("data")} for img in images]
            content = [prompt_text] + image_parts
            response = gemini_model.generate_content(
                content,
                request_options={"timeout": 45},
            )
        else:
            response = gemini_model.generate_content(
                chat_contents,
                request_options={"timeout": 45},
            )
        if response and response.text:
            return response.text.strip()
        return "No response generated from AI."
    except Exception as exc:
        raise RuntimeError(f"Gemini API generation failed: {exc}") from exc


def _generate_openai(
    model: str,
    messages: List[Dict[str, Any]],
    temp: float,
    max_tokens: int,
    images: list = None,
) -> str:
    api_key, base_url, source = resolve_provider_credential("openai")
    if not api_key:
        raise RuntimeError("OPENAI API key is not configured in database credentials or environment variables.")
    import requests
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    if images and formatted_messages:
        import base64
        last_msg = formatted_messages[-1]
        text_content = last_msg.get("content", "")
        parts = [{"type": "text", "text": text_content}]
        for img in images:
            b64 = img.get("data")
            if isinstance(b64, bytes):
                b64 = base64.b64encode(b64).decode("utf-8")
            parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img.get('mime_type', 'image/jpeg')};base64,{b64}"}
            })
        last_msg["content"] = parts

    payload = {
        "model": model or "gpt-4o-mini",
        "messages": formatted_messages,
        "temperature": float(temp) if temp is not None else 0.7,
        "max_tokens": int(max_tokens) if max_tokens else 2048,
    }
    endpoint = f"{base_url.rstrip('/')}/chat/completions" if base_url else "https://api.openai.com/v1/chat/completions"
    res = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    if res.status_code != 200:
        raise RuntimeError(f"OpenAI API error: {res.text}")
    data = res.json()
    return data["choices"][0]["message"]["content"].strip()


def _generate_anthropic(
    model: str,
    messages: List[Dict[str, Any]],
    temp: float,
    max_tokens: int,
    images: list = None,
) -> str:
    api_key, base_url, source = resolve_provider_credential("anthropic")
    if not api_key:
        raise RuntimeError("ANTHROPIC API key is not configured in database credentials or environment variables.")
    import requests
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    system_prompt = ""
    chat_msgs = []
    for m in messages:
        if m.get("role") == "system":
            system_prompt = m.get("content", "")
        else:
            chat_msgs.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    
    if images and chat_msgs:
        import base64
        last_msg = chat_msgs[-1]
        text_content = last_msg.get("content", "")
        parts = []
        for img in images:
            b64 = img.get("data")
            if isinstance(b64, bytes):
                b64 = base64.b64encode(b64).decode("utf-8")
            parts.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.get("mime_type", "image/jpeg"),
                    "data": b64,
                }
            })
        parts.append({"type": "text", "text": text_content})
        last_msg["content"] = parts

    payload = {
        "model": model or "claude-3-5-haiku-latest",
        "messages": chat_msgs,
        "max_tokens": int(max_tokens) if max_tokens else 2048,
        "temperature": float(temp) if temp is not None else 0.7,
    }
    if system_prompt:
        payload["system"] = system_prompt
    endpoint = f"{base_url.rstrip('/')}/messages" if base_url else "https://api.anthropic.com/v1/messages"
    res = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    if res.status_code != 200:
        raise RuntimeError(f"Anthropic API error: {res.text}")
    data = res.json()
    return data["content"][0]["text"].strip()


def generate_response(
    provider: str,
    model: str,
    messages: List[Dict[str, Any]],
    temp: float,
    max_tokens: int,
    images: list = None,
) -> str:
    """
    Adapter interface to generate LLM completions across configured providers.
    - provider == 'mock': Returns mock educational response (Bangla-aware).
    - provider == 'gemini': Calls Google Gemini.
    - provider == 'openai': Calls OpenAI Chat Completions API.
    - provider == 'anthropic': Calls Anthropic Messages API.
    """
    if images is None:
        images = []

    prov = (provider or "mock").strip().lower()

    if prov == "mock":
        user_msg = next((m.get("content") for m in reversed(messages) if m.get("role") == "user"), "")
        sys_msg = next((m.get("content") for m in messages if m.get("role") == "system"), "")

        is_bangla = (
            "bangla" in sys_msg.lower()
            or "বাংলা" in sys_msg
            or "bangla" in user_msg.lower()
            or "বাংলা" in user_msg
        )
        if is_bangla:
            reply = (
                f"এটি বাংলাদেশ আইনি নির্দেশিকা এআই (মক ইঞ্জিন) থেকে একটি আইনি পর্যালোচনা।\n"
                f"কনফিগার করা মডেল: {model or 'mock-model'}\n"
                f"প্রাপ্ত প্রশ্ন: {user_msg}\n\n"
                "আইনি বিশ্লেষণ: বাংলাদেশে দেওয়ানি মামলা ও বিরোধসমূহ দেওয়ানি কার্যবিধি ১৯০৮ (CPC) এবং তামাদি আইন ১৯০৮ অনুযায়ী পরিচালিত হয়। "
                "নির্দিষ্ট প্রতিকারের জন্য তামাদি আইনের সময়সীমা কঠোরভাবে প্রযোজ্য। যেকোনো আইনি কার্যক্রমের জন্য একজন বিজ্ঞ রেজিস্ট্রার্ড আইনজীবীর পরামর্শ নিন।"
            )
        else:
            reply = (
                f"This is a response from BD Legal Guide AI (mock provider).\n"
                f"Configured Model: {model or 'mock-model'}\n"
                f"Prompt received: {user_msg}\n\n"
                "Legal Analysis: In Bangladesh, civil suits are governed by the Code of Civil Procedure 1908 and the Limitation Act 1908. "
                "Please consult a registered advocate for formal litigation advice."
            )
        if images:
            reply += f" [{len(images)} image attachment(s) received.]"
        return reply

    if prov == "gemini":
        return _generate_gemini(model, messages, temp, max_tokens, images=images)

    if prov == "openai":
        return _generate_openai(model, messages, temp, max_tokens, images=images)

    if prov == "anthropic":
        return _generate_anthropic(model, messages, temp, max_tokens, images=images)

    if prov == "openrouter":
        return _generate_openai(model, messages, temp, max_tokens, images=images)

    raise ValueError(f"Unsupported LLM provider: '{provider}'. Supported: mock, gemini, openai, anthropic.")


def self_evaluate(
    provider: str,
    model: str,
    question: str,
    answer: str,
    temp: float = 0.2,
) -> dict | None:
    """
    Self-evaluates the confidence of the assistant answer against the user question.
    Returns {"confidence": int (0-100), "reason": str} or None on any error.
    """
    try:
        prov = (provider or "mock").strip().lower()
        if prov == "mock":
            return {
                "confidence": 85,
                "reason": "Mock self-evaluation for demonstration.",
            }

        prompt = (
            "You are a calibration evaluator. Given a user question and an "
            "assistant answer about Bangladesh law, rate the assistant's "
            "confidence that the answer is accurate and relevant.\n"
            'Respond ONLY with JSON: {"confidence": <int 0-100>, "reason": "<one sentence>"}.\n\n'
            f"User Question:\n{question}\n\n"
            f"Assistant Answer:\n{answer}"
        )

        raw_response = generate_response(
            provider=prov,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temp=temp,
            max_tokens=256,
        )

        match = re.search(r"\{[^{}]*\}", raw_response, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            if "confidence" in data and "reason" in data:
                conf = int(data["confidence"])
                return {
                    "confidence": max(0, min(100, conf)),
                    "reason": str(data["reason"]).strip(),
                }
        return None
    except Exception:
        return None

