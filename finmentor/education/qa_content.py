"""
Static financial-literacy content used by the /learn command and as
grounding context the AI layer can quote from (so explanations stay
accurate even if the model itself is small/uncertain).

This is intentionally plain data, not AI-generated, so it's a stable base
you can expand with more topics or use to fine-tune the local model later
(see README "Next steps").
"""

TOPICS = {
    "diversification": {
        "title_fa": "تنوع‌بخشی چیست؟",
        "body_fa": (
            "تنوع‌بخشی یعنی پول رو بین چند نوع دارایی مختلف (مثلاً سهام، طلا، ارز، "
            "پس‌انداز نقدی) پخش کنی، به‌جای اینکه همه رو روی یک گزینه بذاری. اگه یکی "
            "از دارایی‌ها افت کنه، بقیه می‌تونن ضررو جبران کنن. این یکی از پایه‌ای‌ترین "
            "اصول مدیریت ریسکه."
        ),
    },
    "risk": {
        "title_fa": "ریسک در سرمایه‌گذاری یعنی چه؟",
        "body_fa": (
            "ریسک یعنی احتمال اینکه ارزش دارایی‌ات کم بشه یا حتی از دست بره. معمولاً "
            "دارایی‌هایی که سود بالاتری وعده می‌دن (مثل کریپتو)، ریسک بیشتری هم دارن. "
            "قانون کلی: هیچ‌وقت پولی که برای هزینه‌های ضروری نزدیک لازمشو داری رو "
            "درگیر دارایی‌های پرریسک نکن."
        ),
    },
    "short_vs_long_term": {
        "title_fa": "سرمایه‌گذاری کوتاه‌مدت در برابر بلندمدت",
        "body_fa": (
            "سرمایه‌گذاری کوتاه‌مدت یعنی افق زمانی چند ماه تا یک سال، معمولاً نوسان و "
            "ریسکش بیشتر حس می‌شه. بلندمدت (چند سال به بالا) معمولاً به دارایی فرصت "
            "می‌ده نوسان‌های کوتاه‌مدت رو جبران کنه. افق زمانی هدف مالی‌ات باید نوع "
            "دارایی مناسب رو تعیین کنه، نه برعکس."
        ),
    },
    "emergency_fund": {
        "title_fa": "صندوق اضطراری چیست؟",
        "body_fa": (
            "قبل از هر نوع سرمایه‌گذاری، توصیه‌ی رایج اینه که معادل ۳ تا ۶ ماه هزینه‌ی "
            "زندگی رو به‌صورت نقد و به‌راحتی قابل‌برداشت کنار بذاری. این صندوق، نه سود "
            "بالا هدفشه نه رشد — فقط امنیته."
        ),
    },
}


def list_topics() -> list:
    return [{"key": key, "title": val["title_fa"]} for key, val in TOPICS.items()]


def get_topic(key: str) -> dict:
    return TOPICS.get(key)
