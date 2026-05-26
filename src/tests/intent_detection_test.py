import pytest
from core.router import IntentRouter, Intent

TEST_CASES = [
    ("سلام وقت بخیر خسته نباشید", Intent.GENERAL),
    ("شیر فلکه زبانه لاستیکی فاراب سایز ۳ اینچ چقدر برامون درمیاد؟", Intent.PRICING),
    ("شرایط پرداخت با چک صیادی به چه صورته؟", Intent.FAQ),
    ("کاتالوگ فنی شیر پروانه‌ای ویفری میراب رو می‌خواستم", Intent.TECHNICAL),
]

@pytest.mark.parametrize("user_message, exepted_intent", TEST_CASES)
def test_intent(user_message, exepted_intent):

    router = IntentRouter()
    result = router.route_message(user_message)

    assert result.intent == exepted_intent
    assert len(result.reasoning) > 0


    