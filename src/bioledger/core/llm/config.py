from __future__ import annotations

from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """Provider-specific settings. Only configure providers you use."""

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    # Google
    google_project: str = ""  # GCP project ID (if using Vertex AI)
    google_location: str = "us-central1"
    # General
    api_timeout: int = 120  # seconds


class LLMConfig(BaseModel):
    """LLM settings — nested inside BioLedgerConfig, not standalone.
    All model strings use litellm format: 'provider:model' or 'provider/model'.
    API keys come from env vars (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)."""

    default_model: str = "openai:gpt-4o"
    temperature: float = 0.1
    max_tokens: int = 4096

    # Per-task model overrides — use cheaper/faster models for utility tasks,
    # more capable models for conversational/generation tasks.
    # Keys match task names; absent keys fall back to default_model.
    task_models: dict[str, str] = Field(
        default_factory=lambda: {
            # Conversational (needs reasoning + context understanding)
            "chat": "openai:gpt-4o",
            # Generation (needs structured output accuracy)
            "generate_spec": "openai:gpt-4o",
            # Utility tasks (cheaper, faster)
            "parse_fallback": "openai:gpt-4o-mini",
            "fix_issues": "openai:gpt-4o-mini",
            "review": "openai:gpt-4o-mini",
            "enrich_export": "openai:gpt-4o-mini",
            "ontology_reformulate": "openai:gpt-4o-mini",
            # LLM-as-judge (needs strong reasoning)
            "eval_judge": "openai:gpt-4o",
        }
    )

    # Fallback chain — if primary model fails, try these in order.
    fallback_models: list[str] = Field(
        default_factory=lambda: [
            "anthropic:claude-sonnet-4-20250514",
            "gemini/gemini-2.0-flash",
        ]
    )

    provider: ProviderConfig = ProviderConfig()

    def model_for_task(self, task: str) -> str:
        """Get the model string for a specific task, falling back to default."""
        return self.task_models.get(task, self.default_model)
