"""`_reply` must never lose an answer to a Markdown parse error.

Dynamic text — a model answer, a safety-downgraded context render, a
user-entered goal name — can carry a stray `_`/`*`/`` ` `` Telegram's legacy
Markdown parser can't balance. That happened live: a downgraded /ask answer
failed to send and the user got nothing. `_reply` must retry as plain text
rather than raise.
"""
import pytest
from telegram.error import BadRequest

from app.bot import handlers

UNBALANCED_MARKDOWN_ERROR = BadRequest(
    "Can't parse entities: can't find end of the entity starting at byte offset 421"
)


class _RecordingMessage:
    """Raises on the first (Markdown) send, then succeeds on the plain retry."""

    def __init__(self, fail_first: bool):
        self.calls: list[dict] = []
        self._fail_first = fail_first

    async def reply_text(self, text, **kwargs):
        self.calls.append({"text": text, **kwargs})
        if self._fail_first and len(self.calls) == 1:
            raise UNBALANCED_MARKDOWN_ERROR
        return self


class _Update:
    def __init__(self, message):
        self.effective_message = message


@pytest.mark.asyncio
async def test_unparseable_markdown_falls_back_to_plain_text():
    message = _RecordingMessage(fail_first=True)
    text = "You're saving 35% of your income (debt_management: Strong)."

    await handlers._reply(_Update(message), text)

    assert len(message.calls) == 2
    assert message.calls[0]["parse_mode"] == handlers.PARSE_MODE
    assert "parse_mode" not in message.calls[1]
    assert message.calls[1]["text"] == text          # nothing lost, nothing altered


@pytest.mark.asyncio
async def test_normal_markdown_sends_once():
    message = _RecordingMessage(fail_first=False)

    await handlers._reply(_Update(message), "*Health*: 62.3/100")

    assert len(message.calls) == 1
    assert message.calls[0]["parse_mode"] == handlers.PARSE_MODE


@pytest.mark.asyncio
async def test_an_unrelated_bad_request_is_not_swallowed():
    class AlwaysFails:
        async def reply_text(self, text, **kwargs):
            raise BadRequest("Message is too long")

    with pytest.raises(BadRequest, match="too long"):
        await handlers._reply(_Update(AlwaysFails()), "hello")
