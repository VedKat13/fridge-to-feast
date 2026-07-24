"""
Fridge → Feast
A recipe generator that turns whatever's in your fridge into a written recipe card,
streamed live from an LLM.

Backend: FastAPI. Serves the static frontend and exposes /api/generate, which streams
tokens from the model as Server-Sent Events so the recipe card fills in progressively.
"""

import json
import os
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()

# Groq exposes an OpenAI-compatible endpoint, so the standard OpenAI SDK works
# as-is by pointing base_url at Groq. This keeps the code portable — swapping to
# OpenAI, Anthropic-via-proxy, or another OpenAI-compatible provider only means
# changing these two environment variables.
API_KEY = os.getenv("GROQ_API_KEY")
API_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

if not API_KEY:
    # Fail loudly on startup rather than on the first request — easier to debug
    # during deployment.
    print("WARNING: GROQ_API_KEY is not set. /api/generate will return errors.")

client = OpenAI(api_key=API_KEY or "missing-key", base_url=API_BASE_URL)

app = FastAPI(title="Fridge to Feast")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """You are a warm, practical home-cooking assistant. A user will tell \
you what ingredients they have, and you write ONE recipe that makes good use of them.

Rules:
- Assume basic pantry staples (salt, pepper, cooking oil, water) are available even \
if not listed.
- Keep instructions realistic for a home cook with basic equipment.
- Make the instructions detailed and step-by-step.
- Include clear ingredient amounts in the steps when useful, especially spoon-based \
    amounts like teaspoons and tablespoons.
- Mention active cooking time and waiting/resting time clearly whenever a step \
    involves simmering, baking, marinating, cooling, or chilling.
- Use a standard serving size of 1 bowl or 1 plate per serving and keep nutrition \
    values per serving.
- Include exact estimated nutrition per serving with calories, protein, carbs, fat, \
    fiber, sugar, and sodium.
- Include a short kitchen tools section.
- Respect any dietary restrictions strictly — never suggest an ingredient that \
violates one.
- Do not add extra commentary before or after the recipe. Output ONLY the recipe in \
the exact markdown structure below, with no preamble.

Output format (follow exactly):

## {Recipe Name}
*{One evocative sentence describing the dish.}*

**Servings:** {n}
**Standard serving size:** {about 250 g cooked food, roughly 1 bowl or 1 plate}
**Prep:** {n} min
**Cook:** {n} min
**Rest:** {n} min
**Calories:** ~{n} kcal
**Difficulty:** {Easy, Medium, or Hard}

### Kitchen Tools
- {item}
- {item}

### Ingredients
- {item}
- {item}

### Instructions
1. {step}
2. {step}

### Nutrition
- Calories: {n} kcal
- Protein: {n} g
- Carbohydrates: {n} g
- Fat: {n} g
- Fiber: {n} g
- Sugar: {n} g
- Sodium: {n} mg

### Chef's Tip
{One short, genuinely useful tip specific to this dish.}
"""


class RecipeRequest(BaseModel):
    ingredients: List[str] = Field(..., min_length=1)
    cuisine: Optional[str] = "Any"
    dietary: List[str] = []
    servings: int = 2
    extra_instructions: Optional[str] = ""
    variation_mode: bool = False
    previous_titles: List[str] = []


def build_user_prompt(req: RecipeRequest) -> str:
    parts = [f"Ingredients available: {', '.join(req.ingredients)}."]
    if req.cuisine and req.cuisine.lower() != "any":
        parts.append(f"Cuisine preference: {req.cuisine}.")
    if req.dietary:
        parts.append(f"Dietary restrictions: {', '.join(req.dietary)}.")
    parts.append(f"Servings needed: {req.servings}.")
    if req.extra_instructions and req.extra_instructions.strip():
        parts.append(f"Extra user instructions: {req.extra_instructions.strip()}.")
    if req.variation_mode:
        parts.append(
            "Create a noticeably different recipe from the previous result. "
            "Prefer a different cooking method, flavor profile, or structure if possible."
        )
    if req.previous_titles:
        parts.append(
            "Do not repeat or closely resemble these recent recipe titles: "
            + ", ".join(req.previous_titles)
            + "."
        )
    return " ".join(parts)


@app.post("/api/generate")
async def generate_recipe(req: RecipeRequest):
    if not API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Server is missing GROQ_API_KEY. Set it in the environment.",
        )
    if not req.ingredients:
        raise HTTPException(status_code=400, detail="Add at least one ingredient.")

    user_prompt = build_user_prompt(req)

    def event_stream():
        try:
            stream = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                stream=True,
                temperature=0.85,
                max_tokens=900,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield f"data: {json.dumps({'token': delta})}\n\n"
        except Exception as exc:  # surface the error to the client stream
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering for real streaming
        },
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": MODEL, "key_configured": bool(API_KEY)}


# Serve the frontend last, so it doesn't shadow the API routes above.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
