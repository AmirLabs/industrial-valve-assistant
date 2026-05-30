import pytest
from src.core.flow_manager import FlowManager

@pytest.fixture
def flow_manager():
    """این فیکسچر یک نمونه زنده از فلو منیجر را برای تست‌ها آماده می‌کند"""
    return FlowManager()

def test_flow_manager_empty_message(flow_manager):
    """سناریو ۱: تست فرستادن پیام خالی (چک کردن گاردریل اول)"""
    response = flow_manager.process_message("   ")
    assert response == "لطفاً پیام خود را به صورت متنی بنویسید."
    print("\n" + "="*50)
    print("▶️ [TEST 1 - EMPTY MESSAGE]")
    print(f"User Input: '   '")
    print(f"Bot Response: {response}")
    print("="*50)

def test_flow_manager_general_intent(flow_manager):
    """سناریو ۲: تست واقعی و زنده نیت عمومی (سلام و احوالپرسی)"""
    user_input = "سلام چت بات عزیز روزت بخیر تو کی هستی؟"
    response = flow_manager.process_message(user_input)
    
    # چِک کردن اینکه خروجی معتبر باشه و کرش نکرده باشه
    assert isinstance(response, str)
    assert len(response) > 0
    
    print("\n" + "="*50)
    print("▶️ [TEST 2 - GENERAL INTENT]")
    print(f"User Input: '{user_input}'")
    print(f"Bot Response:\n{response}")
    print("="*50)
    
def test_flow_manager_brands_query(flow_manager):
    """سناریو ۴: تست زنده استعلام برندهای موجود در پایگاه دانش شرکت (FAQ)"""
    user_input = "برند هایی که دارید چیان؟"
    response = flow_manager.process_message(user_input)
    
    # چِک کردن اینکه سیستم پاسخ متنی برگردانده باشد
    assert isinstance(response, str)
    assert len(response) > 0
    
    print("\n" + "="*50)
    print("▶️ [TEST 4 - BRANDS QUERY (FAQ)]")
    print(f"User Input: '{user_input}'")
    print(f"Bot Response:\n{response}")
    print("="*50)
    
    # یک Assert هوشمندانه: پاسخ نباید خطای Fallback فلو منیجر باشد
    # این یعنی روتر حتماً باید نیت را faq تشخیص داده باشد و دیتایی آمده باشد
    assert "پاسخ‌گویی به این نوع درخواست هنوز راه‌اندازی نشده است" not in response

def test_flow_manager_faq_intent(flow_manager):
    """سناریو ۳: تست واقعی و زنده سوالات متداول شرکت (FAQ)"""
    # این سوال رو بر اساس کلمات کلیدی دیتابیس خودت (مثل میراب یا ویفری) هماهنگ کن
    user_input = "شیر پروانه‌ای ویفری میراب چیست"
    response = flow_manager.process_message(user_input)
    
    assert isinstance(response, str)
    assert len(response) > 0
    
    print("\n" + "="*50)
    print("▶️ [TEST 3 - FAQ INTENT]")
    print(f"User Input: '{user_input}'")
    print(f"Bot Response:\n{response}")
    print("="*50)