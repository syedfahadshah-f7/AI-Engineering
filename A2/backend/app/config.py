"""Runtime configuration, read from environment variables / backend/.env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

PROVIDERS = ("mock", "openrouter")


class ModelSpec(BaseModel):
    key: str  # stable slot id: llm | jev | luna | clef
    model_id: str  # OpenRouter model identifier
    name: str  # display name
    category: str  # "decision" | "llm"
    interface: str  # "decisions" | "chat"
    provider: str  # mock | openrouter
    move_limit: int  # moves this model may make per puzzle
    call_cap: int | None  # max live API requests for the whole experiment (None = unlimited)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # mock       = offline simulation (free; for trying the UI)
    # openrouter = the real, budget-limited experiment
    provider: str = "mock"

    student_name: str = "Syed Fahad Faheem Shah"
    roll_number: str = "23K-0062"

    # ---------------- OpenRouter ----------------
    # Secret: lives only in backend/.env, never sent to the browser.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api"
    jev_model: str = "typesafe/jev-1.13"
    luna_model: str = "openai/gpt-6-luna-decisions"
    clef_model: str = "cloudflare/clef"
    llm_model: str = "anthropic/claude-opus-5.5"
    llm_name: str = "Claude Opus 5.5"

    # Budget from the course instructions, enforced in the backend and persisted
    # on disk (never reset on restart). Every HTTP request counts, including
    # failed requests and retries. Cached responses do not.
    total_call_cap: int = 65
    decision_call_cap: int = 20  # per decision model
    llm_call_cap: int = 5  # Claude
    llm_move_limit: int = 5  # Claude is marked unsolved if not solved in 5 moves

    # ---------------- LLM request options ----------------
    # Reasoning effort for the LLM ("" to omit): minimal|low|medium|high.
    llm_reasoning_effort: str = "medium"
    llm_max_tokens: int = 16000
    # JSON-schema constrained output (enum of the 18 moves). Replies are still
    # strictly validated either way.
    llm_structured_output: bool = True

    # ---------------- Experiment rules (identical for every model) ----------------
    max_moves: int = 20
    recent_moves_window: int = 10
    request_timeout_s: float = 300.0
    # Retries cost budget, so they are off by default. Same policy for every model.
    max_transport_retries: int = 0
    max_invalid_retries: int = 0
    trial_time_limit_s: float = 1800.0  # wall-clock cap per model per puzzle (0 = none)
    race_pause_s: float = 4.0  # pause between puzzles so the results stay on screen (not timed)
    # OpenRouter sessions may contain at most this many puzzles ("one good experiment").
    openrouter_max_puzzles: int = 1

    # Persistent storage
    data_dir: Path = BACKEND_DIR / "data"  # cache.json + usage.json
    results_dir: Path = BACKEND_DIR / "results"
    log_dir: Path = BACKEND_DIR / "logs"
    cache_enabled: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def active_provider(self) -> str:
        p = self.provider.strip().lower()
        if p not in PROVIDERS:
            raise ValueError(f"PROVIDER must be one of {PROVIDERS}, got {self.provider!r}")
        return p

    @property
    def is_mock(self) -> bool:
        return self.active_provider == "mock"

    @property
    def models(self) -> list[ModelSpec]:
        p = self.active_provider
        ids = {"llm": self.llm_model, "jev": self.jev_model, "luna": self.luna_model, "clef": self.clef_model}
        names = {"llm": self.llm_name, "jev": "Jev 1.13", "luna": "GPT-6 Luna Decisions", "clef": "Cloudflare Clef"}
        real = p == "openrouter"
        specs = []
        for key in ("llm", "jev", "luna", "clef"):
            is_llm = key == "llm"
            specs.append(ModelSpec(
                key=key,
                model_id=ids[key],
                name=names[key],
                category="llm" if is_llm else "decision",
                interface="chat" if is_llm else "decisions",
                provider=p,
                move_limit=min(self.max_moves, self.llm_move_limit) if is_llm else self.max_moves,
                call_cap=(self.llm_call_cap if is_llm else self.decision_call_cap) if real else None,
            ))
        return specs


@lru_cache
def get_settings() -> Settings:
    return Settings()
