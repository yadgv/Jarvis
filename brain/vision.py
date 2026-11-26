"""Free picture understanding: Gemini (or GitHub Models) looks at a screenshot
before Claude is ever asked. Used only when those keys are in .env."""
import requests

import config
from brain import providers


def look(image_b64: str, question: str, system: str, media_type: str = "image/jpeg"):
    """The free model's answer, or None if no free vision model could answer."""
    for name in getattr(config, "FREE_VISION", ["gemini", "github"]):
        for target in providers.free_targets(name):
            body = {"model": target["model"], "max_tokens": 600, "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}}]}]}
            body.update(target.get("extra") or {})
            try:
                r = requests.post(target["url"], headers=target["headers"], json=body, timeout=(4, 45))
                if r.status_code != 200:
                    raise providers.backup.ProviderError(f"{target['who']} error {r.status_code}: {r.text[:200]}",
                                                         r.status_code)
                text = (r.json()["choices"][0]["message"].get("content") or "").strip()
            except Exception as e:
                providers.rest(target["rest_key"], e)
                continue
            if text:
                print(f"[vision] {target['who']} looked at it (free)")
                return text
    return None
