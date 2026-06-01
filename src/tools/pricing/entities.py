import logging
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import Optional
from src.config.setting import settings
    
logger = logging.getLogger(__name__)

llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model="gpt-4o", temperature=0)


class ProductEntities(BaseModel):
    product_name: Optional[str] = Field(
        None,
        description="The name of the industrial valve product. Examples: شیرفلکه کشویی, شیر پروانه‌ای ,سوپاپی, ویفری,شیر پیسوار,"
    )
    inch: Optional[str] = Field(
        None,
        description="The size of the product in inches, numbers only. Examples: 2, 3, 0.5"
    )
    pressur_rating: Optional[str] = Field(
        None,
        description="The working pressure rating in PN format. Examples: PN16, PN10, PN25"
    )
    company: Optional[str] = Field(
        None,
        description="The brand or manufacturer of the product. Examples: میراب, فاراب, کیز, سیم"
    )

    def missing_required(self) -> list[str]:
        missing = []
        if not self.product_name:
            missing.append("product_name")
        if not self.inch:
            missing.append("inch")
        return missing


parser = JsonOutputParser(pydantic_object=ProductEntities)

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an entity extraction engine for an industrial valve company. "
     "Extract the following entities from the user input: product_name, inch, pressur_rating, company. "
     "Rules:\n"
     "- Return ONLY valid JSON, no extra text\n"
     "- If an entity is not mentioned, return null for that field\n"
     "- Normalize inch to a number only: '3 اینچ' -> '3', 'سه اینچ' -> '3'\n"
     "- Normalize pressur_rating to PN format: '16 بار' -> 'PN16'\n"
     "- Keep product_name and company in Persian as mentioned\n"
     "{format_instructions}"
     ),
    ("human", "{user_input}")
])

chain = prompt | llm | parser


def extract_entities(user_input: str) -> ProductEntities:
    try:
        result = chain.invoke({
            "user_input": user_input,
            "format_instructions": parser.get_format_instructions()
        })
        return ProductEntities(**result)
    except Exception as e:
        logger.error(f"Entity extraction failed: {e}")
        return ProductEntities()