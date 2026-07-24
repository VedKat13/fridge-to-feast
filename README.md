# Fridge → Feast

Tell it what's in your fridge, and it writes you a recipe — streamed live, word by
word, onto a styled recipe card.

Built for the Vibe Coding: AI Web App on AWS project.

---

## Tech stack

| Layer        | Choice                                                        |
|--------------|-----------------------------------------------------------------|
| Frontend     | Vanilla HTML/CSS/JS (single file, no build step, no framework) |
| Backend      | FastAPI (Python)                                                |
| LLM          | Groq API, `llama-3.3-70b-versatile`, via the OpenAI-compatible SDK |
| Streaming    | Server-Sent Events (`text/event-stream`) from backend to browser |
| Container    | Single Dockerfile, one image serves both frontend and API      |
| Deployment   | AWS App Runner (deploys straight from a container image)       |

The backend is provider-agnostic: because Groq exposes an OpenAI-compatible endpoint,
swapping to OpenAI, or any other OpenAI-compatible provider, is just changing
`LLM_BASE_URL` and `GROQ_MODEL` in the environment — no code changes.

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

The same FastAPI process also serves `static/index.html` at `/`, so the whole app is
one container, one port, one deploy target — no CORS or separate hosting to manage.

## Prompting strategy

The system prompt pins the model to a fixed markdown structure (title, tagline, meta
line, ingredients, numbered steps, one tip) so the frontend's lightweight markdown
renderer can reliably style the output as a recipe card without needing a full
markdown library. The user prompt is assembled from the form fields (ingredients,
cuisine, dietary restrictions, servings) rather than free text, which keeps the model
grounded and avoids prompt injection from arbitrary user input.

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste in your GROQ_API_KEY (free, no card required, from
# https://console.groq.com/keys)

uvicorn main:app --reload --port 8000
```

Open http://localhost:8000

## Running with Docker

```bash
docker build -t fridge-to-feast .
docker run -p 8000:8000 --env-file .env fridge-to-feast
```

Open http://localhost:8000

## Deploying to AWS App Runner

App Runner is the fastest path to a public HTTPS URL for a single container — no
load balancer or VPC setup required, and it's free-tier eligible for light traffic.

**Option A — deploy from a GitHub repo (simplest):**

1. Push this project to a GitHub repo. Make sure `.env` is **not** committed
   (it's already in `.gitignore`).
2. In the AWS Console, go to **App Runner → Create service**.
3. Source: **Source code repository** → connect your GitHub account → select the repo
   and branch.
4. Deployment settings: **Automatic** (redeploys on every push) or **Manual**.
5. Build settings: App Runner will detect the `Dockerfile` automatically — leave
   runtime as "Use a Dockerfile."
6. Service settings:
   - Port: `8000`
   - Environment variables → add `GROQ_API_KEY` with your key (mark as a **Secret**
     value if offered — App Runner supports pulling from AWS Secrets Manager too).
7. Click **Create & deploy**. App Runner builds the image and deploys it — takes a
   few minutes.
8. Once status is "Running," copy the default domain shown (a
   `*.awsapprunner.com` HTTPS URL) — that's your public app URL for the submission.

**Option B — deploy from a pre-built image via ECR:**

```bash
aws ecr create-repository --repository-name fridge-to-feast

aws ecr get-login-password --region <your-region> | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

docker build -t fridge-to-feast .
docker tag fridge-to-feast:latest <account-id>.dkr.ecr.<region>.amazonaws.com/fridge-to-feast:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/fridge-to-feast:latest
```

Then in App Runner, choose **Container registry → Amazon ECR**, select the image,
set port `8000` and the `GROQ_API_KEY` environment variable as above.

**Cost awareness:** App Runner's free usage tier and Groq's free API tier are both
enough for a demo/grading workload. Set an AWS Budget alert (Billing → Budgets →
Create budget) at a low threshold (e.g. $1) as a safety net, per the course
guidelines.

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
│   └── index.html        # Frontend: form, recipe card, SSE client, markdown renderer
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .gitignore
└── .env.example
```
