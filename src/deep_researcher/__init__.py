"""deep-researcher: generic, model-agnostic deep research pipeline."""
from .artifact import DeepResearchArtifact
from .config import RunConfig, load_config
from .core import run_research

__all__ = ["run_research", "RunConfig", "load_config", "DeepResearchArtifact"]
__version__ = "0.1.0"
