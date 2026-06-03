# This file makes the 'models' directory a Python package.
# It also serves as a central point for importing all SQLAlchemy models,
# ensuring they are all loaded into the Base.metadata before the application starts.

from .conversation import Conversation
from .message import Message
from .artifact import Artifact
from .agent import Agent

# You can define a __all__ variable to control what `from .models import *` imports
__all__ = [
    "Conversation",
    "Message",
    "Artifact",
    "Agent",
]