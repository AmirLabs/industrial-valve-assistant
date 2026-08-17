from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from src.config.setting import settings
from src.prompts.intent import intent_detection_prompt
from src.prompts.pending import PENDING_DECISION_PROMPT
from langchain_core.prompts import ChatPromptTemplate

intent_detection_prompt = ChatPromptTemplate.from_template(intent_detection_prompt)
pending_decision_prompt = ChatPromptTemplate.from_template(PENDING_DECISION_PROMPT)

class Intent(str, Enum):
    GENERAL = "general"
    TECHNICAL = "technical"
    PRICING = "pricing"
    FAQ = "faq"

class IntentAnalysis(BaseModel):
    intent: Intent = Field(description="The detected intent of the user message.")


class PendingAction(str, Enum):
    """What the user's message means while a price quote is waiting for an answer."""
    CONTINUE = "continue"     # answers our question
    CANCEL = "cancel"         # gives up on the quote
    PRICING = "pricing"       # asks about a different product instead
    TECHNICAL = "technical"   # switches to an engineering question
    FAQ = "faq"               # switches to a company question
    GENERAL = "general"       # only greets or thanks


class PendingDecision(BaseModel):
    action: PendingAction = Field(
        description="What the user's message means for the waiting price quote."
    )
    normalized_value: Optional[str] = Field(
        default=None,
        description=(
            "Only when action is 'continue': the answer written exactly as one of "
            "the offered options. Empty when the user gave no real value."
        ),
    )
    rewritten_question: Optional[str] = Field(
        default=None,
        description=(
            "Only when the user switched topic: their question rewritten as a full "
            "Persian sentence, with words like 'این دوتا' replaced by real names."
        ),
    )
    about_current_options: bool = Field(
        default=False,
        description="True when the new question is about the product or options we just offered.",
    )


def _format_options(options: Optional[list]) -> str:
    """Turns the option list into one numbered line per choice for the prompt."""
    if not options:
        return "(no options were offered)"
    return "\n".join(f"{i}. {o}" for i, o in enumerate(options, start=1))


class IntentRouter:
    def __init__(self):
        self.llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model='gpt-4o-mini',
            temperature=0.0,
        )
        self.prompt_template = intent_detection_prompt
        self.structured_llm = self.llm.with_structured_output(IntentAnalysis)

        # Second, smaller prompt - used only while a price quote waits for an answer.
        self.pending_prompt_template = pending_decision_prompt
        self.pending_structured_llm = self.llm.with_structured_output(PendingDecision)

    def route_message(self, message: str) -> IntentAnalysis:
        chain = self.prompt_template | self.structured_llm
        response = chain.invoke({"message": message})
        return response

    def route_pending(
        self,
        message: str,
        question_text: str,
        options: Optional[list] = None,
    ) -> PendingDecision:
        """
        Reads one message that arrived while we were waiting for an answer.

        Tells us whether the user answered our question, gave up, or moved to
        another subject - so the caller can keep the price quote alive instead
        of pushing every message into the slot.
        """
        chain = self.pending_prompt_template | self.pending_structured_llm
        return chain.invoke({
            "message": message,
            "question_text": question_text,
            "options": _format_options(options),
        })