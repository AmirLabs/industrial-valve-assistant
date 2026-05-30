import pytest
from src.tools.faq.retriever import get_chat_response

# Global expected answer based on your JSON setup
EXPECTED_BRAND_ANSWER = "به طور کلی ما به صورت واسط با شیرالات برند های سیم ایتالیا فاراب میراب و کیز ایران کار میکنیم "


def test_easy_exact_match():
    # Scenario: Exact match from Layer 1 keywords or Layer 2 exact variants
    user_input = "شما با چه شرکت هایی کار میکنید ؟"
    response = get_chat_response(user_input)
    
    assert response == EXPECTED_BRAND_ANSWER


def test_medium_fuzzy_match():
    # Scenario: Suffixes/prefixes added, word order slightly changed, but core keywords exist
    user_input = "برندهایی که باهاشون کار میکنید رو میگید؟"
    response = get_chat_response(user_input)
    
    assert response == EXPECTED_BRAND_ANSWER


def test_hard_restructured_match():
    # Scenario: Highly rephrased sentence structure, relying heavily on token_set_ratio
    user_input = "لیست مارک های شیرآلاتی که نمایندگی دارید چیه"
    response = get_chat_response(user_input)
    
    assert response == EXPECTED_BRAND_ANSWER