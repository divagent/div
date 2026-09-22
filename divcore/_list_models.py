"""List every Gemini model this key can call generateContent on."""
from app.adapters.gemini import get_gemini_client

client = get_gemini_client()
rows = []
for m in client.models.list():
    methods = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
    name = (m.name or "").replace("models/", "")
    if "generateContent" in methods:
        rows.append((name, getattr(m, "input_token_limit", None), getattr(m, "output_token_limit", None)))

rows.sort()
print(f"{len(rows)} models support generateContent:\n")
for name, itl, otl in rows:
    print(f"  {name}")
