from pydantic import BaseModel


AGENT_CONFIG_KEY = "agent_config"


class AgentConfig(BaseModel):
    """Which agents are enabled + their API keys (stored in DB)."""
    claude_enabled: bool = True
    gpt4o_enabled: bool = False
    grok_enabled: bool = False
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    xai_api_key: str = ""


class AgentConfigResponse(BaseModel):
    """What the frontend receives: enabled flags + whether each key is set."""
    claude_enabled: bool
    gpt4o_enabled: bool
    grok_enabled: bool
    anthropic_key_set: bool
    openai_key_set: bool
    xai_key_set: bool


class AgentConfigUpdateRequest(BaseModel):
    """What the frontend sends to update agent config."""
    claude_enabled: bool | None = None
    gpt4o_enabled: bool | None = None
    grok_enabled: bool | None = None
    # Empty string means "clear key", None means "leave unchanged"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    xai_api_key: str | None = None


def default_agent_config() -> AgentConfig:
    return AgentConfig()
