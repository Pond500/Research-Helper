"""
This module provides a function to get a model based on the configuration.
"""

import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI


from src.lib.state import AgentState

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Default chat model. Override per-deployment without code changes:
#   OPENROUTER_MODEL — slug used when routing through OpenRouter (e.g. "anthropic/claude-sonnet-4.6")
#   OPENAI_MODEL     — model used when calling OpenAI directly
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

def get_model(state: AgentState) -> BaseChatModel:
    """
    Get a model based on the environment variable.
    """

    state_model = state.get("model", "openai")
    model = os.getenv("MODEL", state_model)

    if model == "openai":
        if OPENROUTER_API_KEY:
            return ChatOpenAI(
                temperature=0,
                model=OPENROUTER_MODEL,
                api_key=OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
            )
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        return ChatOpenAI(temperature=0, model=OPENAI_MODEL, api_key=OPENAI_API_KEY)
    if model == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        return ChatAnthropic(
            temperature=0,
            model_name="claude-3-5-sonnet-20240620",
            timeout=None,
            stop=None,
        )
    if model == "google_genai":
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        return ChatGoogleGenerativeAI(
            temperature=0,
            model="gemini-1.5-pro",
            api_key=GOOGLE_API_KEY,
        )

    raise ValueError("Invalid model specified")
