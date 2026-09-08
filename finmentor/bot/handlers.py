"""
Telegram command handlers. Kept thin on purpose — all real logic lives in
data/, analysis/, ai/, finance/, education/ so those layers stay testable
without spinning up a bot at all.
"""
from telegram import Update
from telegram.ext import ContextTypes

from ai import combiner
from analysis.technical_indicators import analyze, rank_watchlist
from config import settings
from data.market_data import fetch_watchlist
from education import qa_content
from finance.budget_planner import plan_budget

WELCOME = (
    "سلام! من دستیار هوشمند مالی هستم 👋\n\n"
    "دستورها:\n"
    "/watchlist — روند اخیر دارایی‌های زیر نظر\n"
    "/ask <سوال> — پرسش آزاد درباره‌ی بازار یا مفاهیم مالی\n"
    "/learn — آموزش مفاهیم پایه‌ی سرمایه‌گذاری\n"
    "/budget <درآمد ماهانه> — پیشنهاد تخصیص بودجه\n\n"
    "⚠️ این ربات آموزشیه، نه توصیه‌گر رسمی سرمایه‌گذاری."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("در حال بررسی بازار... ⏳")
    raw = fetch_watchlist(settings.stock_watchlist, settings.crypto_watchlist, days=30)
    reports = [analyze(symbol, points) for symbol, points in raw.items() if points]
    ranked = rank_watchlist(reports)

    lines = ["📊 روند اخیر (نه پیش‌بینی آینده):\n"]
    for r in ranked:
        arrow = {"uptrend": "🔼", "downtrend": "🔽", "sideways": "➡️"}[r.trend_label]
        lines.append(
            f"{arrow} {r.symbol}: {r.pct_change_period:+.2f}٪ در ۳۰ روز اخیر "
            f"(نوسان: {r.volatility}%)"
        )
    lines.append("\n⚠️ این فقط تحلیل روند گذشته‌ست، نه تضمین آینده.")
    await update.message.reply_text("\n".join(lines))


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text("بعد از /ask سوالتو بنویس. مثال:\n/ask روند طلا تو یک ماه اخیر چطور بوده؟")
        return
    await update.message.reply_text("در حال فکر کردن... 🤔")
    result = combiner.answer(question)
    await update.message.reply_text(result["text"])


async def learn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        key = context.args[0]
        topic = qa_content.get_topic(key)
        if not topic:
            await update.message.reply_text("این موضوع رو ندارم. با /learn لیست موضوعات رو ببین.")
            return
        await update.message.reply_text(f"*{topic['title_fa']}*\n\n{topic['body_fa']}", parse_mode="Markdown")
        return

    topics = qa_content.list_topics()
    lines = ["📚 موضوعات آموزشی (با /learn <کلید> بازش کن):\n"]
    lines += [f"• {t['key']} — {t['title']}" for t in topics]
    await update.message.reply_text("\n".join(lines))


async def budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("بعد از /budget درآمد ماهانه‌تو بنویس. مثال:\n/budget 15000000")
        return
    try:
        income = float(context.args[0])
    except ValueError:
        await update.message.reply_text("لطفاً فقط عدد بفرست. مثال:\n/budget 15000000")
        return

    plan = plan_budget(income)
    text = (
        f"💰 پیشنهاد تخصیص بودجه برای درآمد {income:,.0f}:\n\n"
        f"ضروریات: {plan.needs:,.0f}\n"
        f"هزینه‌های دلخواه: {plan.wants:,.0f}\n"
        f"پس‌انداز/سرمایه‌گذاری: {plan.savings:,.0f}\n\n"
        f"{plan.notes}\n\n"
        f"پس‌انداز تخمینی یک سال: {plan.monthly_savings_in_a_year:,.0f}"
    )
    await update.message.reply_text(text)
