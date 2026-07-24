# Fridge → Feast

Fridge → Feast turns a list of ingredients into a streamed recipe card, word by
word, in the browser.

This project was built for the Vibe Coding: AI Web App project.

---

## Tech stack

| Layer        | Choice                                                        |
|--------------|-----------------------------------------------------------------|
| Frontend     | Vanilla HTML/CSS/JS (single file, no build step, no framework) |
| Backend      | FastAPI (Python)                                                |
| LLM          | Groq API, `llama-3.3-70b-versatile`, via the OpenAI-compatible SDK |
| Streaming    | Server-Sent Events (`text/event-stream`) from backend to browser |
| Container    | Single Dockerfile, one image serves both frontend and API      |
| Packaging    | Single repo with one backend, one static frontend, one port    |

The backend is provider-agnostic. Because Groq exposes an OpenAI-compatible
endpoint, switching to OpenAI or another compatible provider only requires
changing `LLM_BASE_URL` and `GROQ_MODEL` in the environment.

## Architecture

```
Browser (static/index.html)
   │  fetch POST /api/generate  (ingredients, cuisine, dietary, servings)
   ▼
FastAPI (main.py)
   │  builds a system + user prompt
   │  calls client.chat.completions.create(..., stream=True)
   ▼
Groq API  ──────────────────────────────────────────►  streams tokens back
   │
   ▼
FastAPI re-emits each token as an SSE `data: {"token": "..."}` event
   │
   ▼
Browser reads the stream, appends tokens, re-renders the recipe card live
```

The same FastAPI process also serves `static/index.html` at `/`, keeping the whole
app in one place with no CORS or separate frontend/backend hosting to manage.

## Prompting strategy

The system prompt pins the model to a fixed markdown structure (title, tagline,
meta line, ingredients, numbered steps, one tip) so the frontend's lightweight
markdown renderer can reliably style the output as a recipe card without needing a
full markdown library. The user prompt is assembled from form fields (ingredients,
cuisine, dietary restrictions, servings) rather than free text, which keeps the
model grounded and reduces prompt-injection risk from arbitrary user input.

## Current Features

- Detailed recipe output with separate prep time, cook time, rest time, and calorie estimate.
- Step-by-step instructions with more precise quantities and timing cues.
- A nutrition summary and a kitchen tools section in the recipe card.
- Quick serving presets for 1, 2, 4, and 6 servings.
- An "Other instructions" input for custom recipe directions.
- Copy, save, and print actions for the generated recipe.
- A saved output panel for copying previously saved recipes later.
- A clickable YouTube recipe search link below the generated card.
- A "New recipe" button that asks for a different variation using the same ingredients.

## Environment variables

| Variable        | Required | Default                              |
|------------------|----------|---------------------------------------|
| `GROQ_API_KEY`   | Yes      | —                                     |
| `GROQ_MODEL`     | No       | `llama-3.3-70b-versatile`             |
| `LLM_BASE_URL`   | No       | `https://api.groq.com/openai/v1`      |

## Project structure

```
fridge-to-feast/
├── main.py              # FastAPI app: streaming endpoint + static file serving
├── static/
│   ├── favicon.svg       # Browser tab icon
│   └── index.html        # Frontend: form, recipe card, SSE client, markdown renderer
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .gitignore
└── .env.example
```
