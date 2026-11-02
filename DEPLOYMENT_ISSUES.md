# GraphMind — Deployment Issues & Resolutions

> A chronological record of every significant problem encountered while deploying the
> **MetaKGP GraphRAG Agent (GraphMind)** on Railway (backend) and Vercel (frontend),
> and while integrating the Google Gemini API under the free-tier limits.

---

## Table of Contents

1. [Deployment Issues](#1-deployment-issues)
   - [1.1 `postgres://` scheme rejected by SQLAlchemy 2.0](#11-postgres-scheme-rejected-by-sqlalchemy-20)
   - [1.2 `DATABASE_URL` missing at startup crashed the container](#12-databaseurl-missing-at-startup-crashed-the-container)
   - [1.3 Docker image failed to build — `build-essential` missing for binary packages](#13-docker-image-failed-to-build--build-essential-missing-for-binary-packages)
   - [1.4 Non-root Docker user could not write to `/app/data`](#14-non-root-docker-user-could-not-write-to-appdata)
   - [1.5 Health check failing — Railway killed the container before the app finished loading](#15-health-check-failing--railway-killed-the-container-before-the-app-finished-loading)
   - [1.6 `PRODUCTION` flag unset — session cookies not marked `Secure`, breaking OAuth in HTTPS](#16-production-flag-unset--session-cookies-not-marked-secure-breaking-oauth-in-https)
   - [1.7 Google OAuth `redirect_uri_mismatch` (Error 400) on deployed site](#17-google-oauth-redirect_uri_mismatch-error-400-on-deployed-site)
   - [1.8 OAuth CSRF `mismatching_state` errors on callback](#18-oauth-csrf-mismatching_state-errors-on-callback)
   - [1.9 CORS blocking API calls from the Vercel frontend](#19-cors-blocking-api-calls-from-the-vercel-frontend)
   - [1.10 Alternate Railway DATABASE_URL variable names also using wrong scheme](#110-alternate-railway-databaseurl-variable-names-also-using-wrong-scheme)
   - [1.11 Windows console UnicodeEncodeError during local development](#111-windows-console-unicodeencodeerror-during-local-development)
   - [1.12 Multiple conflicting Railway start-command sources](#112-multiple-conflicting-railway-start-command-sources)
2. [Gemini API Limit Issues](#2-gemini-api-limit-issues)
   - [2.1 429 RESOURCE_EXHAUSTED — free-tier RPM cap hit](#21-429-resource_exhausted--free-tier-rpm-cap-hit)
   - [2.2 503 UNAVAILABLE / high demand transient errors](#22-503-unavailable--high-demand-transient-errors)
   - [2.3 MoE verification loop tripling API call count](#23-moe-verification-loop-tripling-api-call-count)
   - [2.4 GOOGLE_API_KEY vs GEMINI_API_KEY env-var naming inconsistency](#24-google_api_key-vs-gemini_api_key-env-var-naming-inconsistency)
   - [2.5 Model name unrecognised in older SDK versions](#25-model-name-unrecognised-in-older-sdk-versions)
   - [2.6 Multi-part Gemini response content breaking string extraction](#26-multi-part-gemini-response-content-breaking-string-extraction)

---

## 1. Deployment Issues

---

### 1.1 `postgres://` scheme rejected by SQLAlchemy 2.0

**File:** `backend/config.py`, `backend/database.py`

**Symptom:**
On Railway, the automatically injected `DATABASE_URL` begins with `postgres://` (the legacy Heroku-style URL). SQLAlchemy 2.0+ dropped support for this scheme and raises:

```
sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres
```

The backend container started and immediately crashed on the first database operation.

**Root Cause:**
SQLAlchemy 2.0 removed the legacy `postgres://` dialect alias and requires the explicit `postgresql://` scheme.

**Resolution:**
Added a normalisation step in `get_database_url()` that rewrites the scheme before the URL is ever handed to SQLAlchemy:

```python
# backend/config.py
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
```

This runs unconditionally whenever `DATABASE_URL` is resolved, so any Railway-injected URL is transparently corrected.

---

### 1.2 `DATABASE_URL` missing at startup crashed the container

**File:** `backend/database.py`, `backend/main.py`

**Symptom:**
When `DATABASE_URL` was not yet set (e.g. first deploy before the PostgreSQL add-on was linked), engine creation raised an unhandled `ArgumentError` during module import. Uvicorn never started, the health check endpoint never became reachable, and Railway kept restarting the container in an infinite crash loop.

**Root Cause:**
`create_engine("")` raises `ArgumentError` synchronously at import time, killing the process before the ASGI application could handle any HTTP requests.

**Resolution:**
Wrapped `create_engine` in a `try/except` inside `create_db_engine()`. On failure it:

1. Sets the module-level flag `db_url_configured = False`.
2. Falls back to an in-memory SQLite engine so the process can boot.
3. Lets the `/` and `/health` routes return `{"status": "degraded"}` so Railway's health check passes.
4. Returns `HTTP 503` from every database-dependent route with a human-readable message.

`Base.metadata.create_all()` is now run inside the FastAPI `lifespan` handler with retry logic (5 attempts, 2 s delay each) rather than at module import, giving the database container time to start:

```python
# backend/main.py — lifespan handler
for attempt in range(1, max_retries + 1):
    try:
        Base.metadata.create_all(bind=engine)
        db_connected = True
        break
    except Exception as exc:
        time.sleep(retry_delay)
```

---

### 1.3 Docker image failed to build — `build-essential` missing for binary packages

**File:** `Dockerfile`

**Symptom:**
`pip install` for packages like `psycopg2-binary`, `bcrypt`, and `chromadb` failed during `docker build`:

```
gcc: error: ...
error: command 'gcc' failed with exit status 1
```

**Root Cause:**
The base `python:3.11-slim` image ships without C compilers. Several Python packages compile C extensions at install time.

**Resolution:**
Introduced a two-stage Dockerfile:

- **Stage 1 (builder):** installs `build-essential` and `curl`, then builds the virtual environment in `/opt/venv`.
- **Stage 2 (runner):** copies only `/opt/venv` from the builder — no compilers in the final image, keeping the runtime image small and secure.

```dockerfile
FROM python:3.11-slim AS builder
RUN apt-get install -y build-essential curl
RUN python -m venv /opt/venv && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.11-slim AS runner
COPY --from=builder /opt/venv /opt/venv
```

---

### 1.4 Non-root Docker user could not write to `/app/data`

**File:** `Dockerfile`

**Symptom:**
After switching the container to run as a non-root user (`appuser`, UID 10001) for security, the ChromaDB persistence directory (`/app/data/chroma_db`) raised `PermissionError` at runtime.

**Root Cause:**
Directories created by `root` during the Docker build are not writable by a non-root user unless ownership is explicitly transferred.

**Resolution:**
Added an explicit `chown` + `mkdir` step before switching users, and used `COPY --chown` for all application files:

```dockerfile
RUN mkdir -p /app/data/raw /app/data/processed /app/data/chroma_db && \
    chown -R appuser:appgroup /app/data

COPY --chown=appuser:appgroup backend/ ./backend/
COPY --chown=appuser:appgroup data/chroma_db/ ./data/chroma_db/
USER appuser
```

---

### 1.5 Health check failing — Railway killed the container before the app finished loading

**File:** `Dockerfile`, `backend/main.py`

**Symptom:**
During initial deployment, Railway's health check pinged `GET /` before Uvicorn had finished initialising — especially while `sentence-transformers` and ChromaDB were loading large model weights. Railway marked the container unhealthy and terminated it.

**Root Cause:**
The Docker `HEALTHCHECK` started almost immediately (`--start-period` too short), and the RAG service was initialised at import time which blocked startup.

**Resolution:**
Two changes applied together:

1. **Lazy initialisation** in `RAGService` — heavy model loading is deferred to the first actual chat request via a `_initialize()` guard:

   ```python
   def chat(self, user_message, history, ...):
       self._initialize()   # no-op after first call
   ```

2. **Increased `--start-period`** in the Dockerfile healthcheck so Railway doesn't count failures during boot:

   ```dockerfile
   HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
       CMD curl -f http://localhost:${PORT:-8000}/ || exit 1
   ```

---

### 1.6 `PRODUCTION` flag unset — session cookies not marked `Secure`, breaking OAuth in HTTPS

**File:** `backend/main.py`

**Symptom:**
On the Railway HTTPS deployment, clicking "Sign in with Google" redirected correctly to Google, but after consent, the browser never sent the session cookie back on the `/auth/google/callback` request. Authlib raised `mismatching_state` because the OAuth state value was missing from the session.

**Root Cause:**
`SessionMiddleware` was configured with `https_only=False` (local-dev default). Modern browsers silently drop `Set-Cookie` headers from HTTPS responses that lack the `Secure` attribute when `SameSite=Lax` is set. The session was written but never read on the callback.

**Resolution:**
Introduced an `IS_PRODUCTION` flag from the `PRODUCTION` environment variable:

```python
IS_PRODUCTION = os.getenv("PRODUCTION", "false").strip().lower() in ("true", "1")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=IS_PRODUCTION,   # True on Railway, False for local http://
    max_age=300,
)
```

Setting `PRODUCTION=true` in Railway's environment variables resolved the cookie issue entirely.

---

### 1.7 Google OAuth `redirect_uri_mismatch` (Error 400) on deployed site

**File:** `backend/config.py`, Google Cloud Console

**Symptom:**
Clicking "Sign in with Google" on the deployed site showed Google's error page:

```
Access blocked: This app's request is invalid
Error 400: redirect_uri_mismatch
```

**Root Cause:**
The `GOOGLE_REDIRECT_URI` environment variable on Railway was still set to the local development value (`http://localhost:8000/auth/google/callback`). Google rejected the OAuth request because the URI didn't match any registered in the Google Cloud Console OAuth client.

**Resolution:**
Two steps, both required and both must match exactly:

1. **Railway environment variable** — set `GOOGLE_REDIRECT_URI` to the production backend URL:
   ```
   GOOGLE_REDIRECT_URI=https://<railway-domain>/auth/google/callback
   ```

2. **Google Cloud Console** → APIs & Services → Credentials → OAuth 2.0 Client → Authorised redirect URIs — add:
   ```
   https://<railway-domain>/auth/google/callback
   ```

No code change was required — `config.py` already reads `GOOGLE_REDIRECT_URI` from the environment.

---

### 1.8 OAuth CSRF `mismatching_state` errors on callback

**File:** `backend/routers/auth_router.py`

**Symptom:**
Some users got redirected back to the frontend with:
```
auth_error=OAuth session expired or was used twice. Please try signing in again.
```

**Root Cause:**
Three separate triggers identified:
- Double-clicking "Sign in with Google" spawned two OAuth flows; the callback for the second found a stale state.
- The 5-minute `max_age` session window expired if the user lingered on the Google consent screen.
- On local dev, navigating between `localhost` and `127.0.0.1` created separate session cookies, so state written on one was invisible to the callback on the other.

**Resolution:**
- Added a hostname-normalisation guard in `google_login` that redirects to the canonical domain of `GOOGLE_REDIRECT_URI` before initiating the OAuth dance, ensuring the session cookie domain is always consistent.
- The `google_callback` handler catches all authlib exceptions and redirects with a friendly error instead of returning 500:

  ```python
  except Exception as exc:
      err_msg = str(exc)
      if "mismatching_state" in err_msg or "CSRF" in err_msg:
          err_msg = "OAuth session expired or was used twice. Please try signing in again."
      return RedirectResponse(url=f"{target_frontend}/?auth_error={quote(err_msg)}")
  ```

---

### 1.9 CORS blocking API calls from the Vercel frontend

**File:** `backend/main.py`

**Symptom:**
After deploying the frontend to Vercel, all browser API calls were blocked:

```
Access to fetch at 'https://<railway-domain>/chat' from origin 'https://<vercel-domain>'
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present.
```

**Root Cause:**
`CORSMiddleware` only listed `localhost` origins from local development. The Vercel production domain was absent.

**Resolution:**
The allowed origins list is built dynamically at startup using the `FRONTEND_URL` environment variable:

```python
_allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if FRONTEND_URL and FRONTEND_URL not in _allowed_origins:
    _allowed_origins.append(FRONTEND_URL)

app.add_middleware(CORSMiddleware, allow_origins=_allowed_origins, ...)
```

Setting `FRONTEND_URL=https://<vercel-domain>` in Railway's variables panel was sufficient — no code change on redeploy needed.

---

### 1.10 Alternate Railway `DATABASE_URL` variable names also using wrong scheme

**File:** `backend/config.py`

**Symptom:**
Even after the scheme fix in §1.1, some deploys received `DATABASE_PRIVATE_URL` or `DATABASE_PUBLIC_URL` instead of `DATABASE_URL`. These alternate variables also started with `postgres://`, triggering the same SQLAlchemy error.

**Resolution:**
`get_database_url()` checks a priority list of Railway-specific variable names and applies scheme normalisation to whichever URL it resolves first:

```python
alt_url = (
    os.getenv("DATABASE_PRIVATE_URL")
    or os.getenv("DATABASE_PUBLIC_URL")
    or os.getenv("POSTGRESQL_URL")
)
if alt_url and (not url or is_placeholder):
    url = alt_url

# Normalisation always applied last, regardless of source
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
```

---

### 1.11 Windows console `UnicodeEncodeError` during local development

**File:** `backend/rag_service.py`

**Symptom:**
On Windows (default `cp1252` console), `print()` calls with Unicode characters from LangGraph debug output or Wikipedia text raised:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2026' in position 14
```

**Root Cause:**
Python on Windows uses the system ANSI code page for `sys.stdout` unless explicitly configured otherwise.

**Resolution:**
Added a one-time reconfiguration guard at module load:

```python
if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
```

This is a no-op on Linux/macOS and in Railway containers (already UTF-8).

---

### 1.12 Multiple conflicting Railway start-command sources

**Files:** `railway.json`, `railpack.json`, `nixpacks.toml`, `Procfile`, `backend/railway.toml`

**Symptom:**
Ambiguity about which start command Railway was actually using. Some deploys used Nixpacks (ignoring the Dockerfile), others used the Dockerfile but with an inconsistent start command.

**Root Cause:**
Multiple configuration files each specified a start command. Railway's builder selection depended on which config file took priority (`DOCKERFILE` vs `NIXPACKS` vs `RAILPACK`), leading to non-deterministic build behaviour.

**Resolution:**
Consolidated to a single source of truth in `railway.json` with `"builder": "DOCKERFILE"` explicitly set. The Dockerfile `CMD` and `railway.json` `startCommand` were aligned:

```dockerfile
# Dockerfile
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
```

```json
// railway.json
{ "deploy": { "startCommand": "uvicorn backend.main:app --host 0.0.0.0 --port $PORT" } }
```

---

## 2. Gemini API Limit Issues

---

### 2.1 `429 RESOURCE_EXHAUSTED` — free-tier RPM cap hit

**File:** `backend/rag_service.py` — `_safe_call()`

**Symptom:**
Under the Gemini free tier, any burst of more than ~5 requests per minute triggered:

```
google.api_core.exceptions.ResourceExhausted: 429 RESOURCE_EXHAUSTED
Quota exceeded for quota metric 'generate_content_request_count'
```

Users received a 500 Internal Server Error with no explanation.

**Root Cause:**
The free tier enforces a **5 RPM hard limit**. With MoE verification enabled, a single user question consumed 3–4 LLM calls (tool call + answer + verifiers), exhausting the quota after just one or two questions in quick succession.

**Resolution:**
Implemented a three-layer mitigation strategy inside `_safe_call()`:

1. **Model fallback cascade** — on 429, automatically switch to a lighter model with its own independent quota:
   ```python
   fallback_chain = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]
   ```

2. **Quota delay wait** — if no fallback remains and the error includes a `retry in Xs` hint (≤ 20 s), sleep and retry once:
   ```python
   delay_match = re.search(r"retry in (\d+(?:\.\d+)?)s", err)
   wait_sec = float(delay_match.group(1)) if delay_match else 16.0
   if wait_sec <= 20.0:
       time.sleep(wait_sec + 1.0)
       return fn()
   ```

3. **Friendly user message** — if all retries are exhausted, return a plain-language explanation instead of raising an exception:
   ```python
   return (
       "Google Gemini free-tier rate limit reached (5 requests/minute). "
       "Please wait ~15 seconds before asking your next question, or upgrade "
       "your Gemini API key in Google AI Studio."
   )
   ```

---

### 2.2 `503 UNAVAILABLE` / "high demand" transient errors

**File:** `backend/rag_service.py` — `_safe_call()`

**Symptom:**
Intermittently (unrelated to quota), the Gemini API returned:

```
503 UNAVAILABLE: The model is overloaded. Please try again later.
```

**Root Cause:**
Google-side transient overload — not a client quota error. Unpredictable and unrelated to usage rate.

**Resolution:**
`_safe_call()` detects `503`/`UNAVAILABLE`/`"high demand"` strings and applies the same model fallback cascade as for 429. If no fallback remains, it returns a friendly message rather than crashing:

```python
is_503 = "503" in err or "UNAVAILABLE" in err or "high demand" in err
if is_503 and next_model:
    # fail over to lighter model
elif is_503:
    return "The Gemini AI model is currently experiencing high demand. Please try again in a few moments."
```

---

### 2.3 MoE verification loop tripling API call count

**File:** `backend/rag_service.py`, `rag/agent.py`

**Symptom:**
With the full Mixture-of-Experts (MoE) pipeline enabled, every user question consumed:
- 1–2 calls for the ReAct agent tool loop
- 1 call for the MoE verifier (3 expert prompts)
- 1 additional call per self-correction retry

This easily exceeded 5 RPM for a single user, making the feature completely unusable on the free tier.

**Root Cause:**
The MoE pipeline was designed for accuracy, not rate-limit awareness. Its call count scales with the number of expert verifiers and retry attempts.

**Resolution:**
MoE verification is now **disabled by default** and controlled via an environment variable:

```python
enable_moe = os.getenv("ENABLE_MOE", "false").strip().lower() in ("true", "1")

if not enable_moe:
    # Streamlined: 1-2 LLM calls per query (ReAct agent only)
    final_state = _safe_call(lambda: self._agent.invoke({"messages": current_messages}))
    return _extract_text(final_state["messages"][-1].content)

# Full MoE loop only when ENABLE_MOE=true
```

Per-query API calls reduced from 3–6 down to **1–2**, sustainable on the free tier. MoE can be re-enabled on a paid key with `ENABLE_MOE=true`.

---

### 2.4 `GOOGLE_API_KEY` vs `GEMINI_API_KEY` env-var naming inconsistency

**File:** `backend/rag_service.py`

**Symptom:**
The `langchain-google-genai` SDK reads `GOOGLE_API_KEY` by default, but the project used `GEMINI_API_KEY`. This caused silent failures where the SDK found no key and returned `401 Unauthorized` or `API key not valid`.

**Root Cause:**
Google's Python SDK standardised on `GOOGLE_API_KEY`, while many tutorials use `GEMINI_API_KEY`. Both names exist in the wild with no clear community consensus.

**Resolution:**
`_initialize()` accepts either variable name with a priority fallback:

```python
api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError(
        "Gemini API key is not set. Please add GEMINI_API_KEY=your_key "
        "(or GOOGLE_API_KEY=your_key) to your .env file."
    )
self._api_key = api_key
```

---

### 2.5 Model name unrecognised in older SDK versions

**File:** `backend/rag_service.py`, `requirements.txt`

**Symptom:**
When testing newer Gemini models, some SDK versions raised:

```
google.api_core.exceptions.NotFound: 404 models/gemini-3.5-flash is not found
```

**Root Cause:**
`langchain-google-genai` versions below `1.0.0` used the `v1beta` API endpoint which did not expose newer model IDs. Model names also must be passed without a `models/` prefix in LangChain's wrapper.

**Resolution:**
- Bumped `langchain-google-genai>=1.0.0` in `requirements.txt` to use the stable `v1` API endpoint.
- Model name (`LLM_MODEL` env var) is passed directly to `ChatGoogleGenerativeAI(model=model_name, ...)` — no prefix manipulation; the SDK handles routing internally.
- The `LLM_MODEL` default was set to `gemini-3.5-flash` in `.env.example` to reflect the verified working value.

---

### 2.6 Multi-part Gemini response content breaking string extraction

**File:** `backend/rag_service.py` — `_extract_text()`

**Symptom:**
Occasionally, especially for answers containing structured data or code blocks, the `content` field of the final LangGraph message was not a plain `str` but a list of content part objects. Downstream code assumed `str` type and displayed raw Python object representations:

```
[{'type': 'text', 'text': 'The halls at IIT KGP are...'}]
```

verbatim in the chat UI.

**Root Cause:**
The Gemini API can return `content` as either a plain string or a list of `Part` objects depending on the response type. LangChain's Gemini integration does not always coerce this to a flat string.

**Resolution:**
Added a robust `_extract_text()` helper that handles all known content shapes:

```python
def _extract_text(raw_content) -> str:
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, list):
        parts = []
        for p in raw_content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict) and "text" in p:
                parts.append(p["text"])
            elif hasattr(p, "text"):
                parts.append(getattr(p, "text"))
        return "\n".join(parts)
    return str(raw_content)
```

Called on every `final_state["messages"][-1].content` before returning the answer to the user.

---

*Last updated: October 2026*
