"""The seven agent architectures. Each is an independent class with its own decision logic."""
from .base import Agent, Decision
from .contextual import ContextualAgent
from .goal_based import GoalBasedAgent
from .hierarchical import HierarchicalAgent
from .learning import Brain, LearningAgent
from .model_based import ModelBasedReflexAgent
from .simple_reflex import SimpleReflexAgent
from .utility_based import UtilityBasedAgent

AGENT_CLASSES = [SimpleReflexAgent, ModelBasedReflexAgent, GoalBasedAgent, UtilityBasedAgent,
                 LearningAgent, HierarchicalAgent, ContextualAgent]
REGISTRY = {c.key: c for c in AGENT_CLASSES}


def make_agent(key: str, brain: "Brain | None" = None) -> Agent:
    """A FRESH agent instance (no state shared between runs). The learning agent gets a copy of `brain`."""
    cls = REGISTRY[key]
    return cls(brain) if cls is LearningAgent else cls()


__all__ = ["Agent", "Decision", "Brain", "AGENT_CLASSES", "REGISTRY", "make_agent"]
