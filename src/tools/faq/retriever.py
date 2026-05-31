import json
from rapidfuzz import fuzz
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from src.config.setting import settings

# Load local knowledge bases
with open("src/data/faq_keywords.json", "r", encoding="utf-8") as file:
    keywords_data = json.load(file)

with open("src/data/faq.json", "r", encoding="utf-8") as file:
    faq_data = json.load(file)

# Initialize LLM component
llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY,model="gpt-4o", temperature=0.2)


def handle_ambiguous_response(user_text: str, options: list) -> str:
    # Prompt to guide the LLM when two potential answers overlap
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert AI assistant for an industrial valve company. "
                   "The user's query is ambiguous. You are provided with the top 2 matching FAQ answers. "
                   "Synthesize a polite response addressing both possibilities separately to help the user."),
        ("human", "User Question: {query}\n\n"
                  "Option 1: {ans1}\n\n"
                  "Option 2: {ans2}")
    ])
    
    chain = prompt | llm | StrOutputParser()
    
    return chain.invoke({
        "query": user_text,
        "ans1": options[0]["answer"],
        "ans2": options[1]["answer"]
    })


def handle_llm_fallback(user_text: str, history: list = None) -> str:
    messages = [("system", "You are a senior technical support engineer at CEC answer the question on your own knowledge")]
    
    if history:
        for msg in history[:-1]:  # exclude last message, it's already user_text
            messages.append((msg["role"], msg["content"]))
    
    messages.append(("human", "{query}"))
    
    prompt = ChatPromptTemplate.from_messages(messages)
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"query": user_text})


def get_chat_response(user_text: str,history: list = None) -> str:
    # Layer 1: Keyword Matching
    for intent_key, intent_data in keywords_data.items():
        for keyword in intent_data["keywords"]:
            if keyword in user_text:
                return intent_data["answer"]

    # Layer 2: Fuzzy Matching Analysis
    HIGH_THRESH = 60.0
    LOW_THRESH = 35.0
    
    high_matches = []
    soft_matches = []

    for intent_key, intent_data in faq_data.items():
        for variant in intent_data["variants"]:
            score = fuzz.token_set_ratio(user_text, variant)
            match_payload = {"intent": intent_key, "answer": intent_data["answer"], "score": score}
            
            if score >= HIGH_THRESH:
                high_matches.append(match_payload)
            elif LOW_THRESH <= score < HIGH_THRESH:
                soft_matches.append(match_payload)

    # Sort candidates by score descending
    high_matches.sort(key=lambda x: x["score"], reverse=True)
    soft_matches.sort(key=lambda x: x["score"], reverse=True)

    # Evaluate matches against business rules
    if high_matches:
        return high_matches[0]["answer"]

    if soft_matches:
        # Deduplicate intents to ensure distinct options
        unique_intents = list({m["intent"]: m for m in soft_matches}.values())
        
        if len(unique_intents) > 1:
            return handle_ambiguous_response(user_text, unique_intents[:2])
        else:
            return unique_intents[0]["answer"]

    # Final Fallback to LLM knowledge
    return handle_llm_fallback(user_text,history=history)