#state.py


from typing import TypedDict, Optional, List, Annotated

from langgraph.graph import add_messages
import operator


class OverallState(TypedDict):

    messages: Annotated[list, add_messages]
    user_id: Optional[str]
    current_course: str

    intent: str
    note_style: str

    search_queries: Annotated[list, operator.add]
    retrieved_docs: Annotated[list, operator.add]
    search_status: str

    draft_output: Optional[str]
    final_output: str
    annotations: List[dict]

    current_step: str
    error: Optional[str]


