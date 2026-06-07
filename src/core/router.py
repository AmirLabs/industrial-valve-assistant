from enum import Enum
from pydantic import BaseModel,Field
from langchain_openai import ChatOpenAI
from src.config.setting import settings
from src.prompts.intent import intent_detection_prompt
from langchain_core.prompts import ChatPromptTemplate

intent_detection_prompt = ChatPromptTemplate.from_template(intent_detection_prompt)

class Intent(str, Enum): 
    GENERAL = "general"
    TECHNICAL = "technical"
    PRICING = "pricing"
    FAQ = "faq"

class IntentAnalysis (BaseModel):
    intent: Intent = Field(description="The detected intent of the user message.")
    reasoning: str = Field(description="Brief explanation of why this intent was chosen.")


class IntentRouter :
    def __init__ (self):
        self.llm = ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model='gpt-4o',
        temperature=0.0,)
        self.prompt_template = intent_detection_prompt
        self.structured_llm = self.llm.with_structured_output(IntentAnalysis)

    def route_message (self, message: str) -> IntentAnalysis:
        chain = self.prompt_template | self.structured_llm
        response = chain.invoke({"message": message})
        return response


