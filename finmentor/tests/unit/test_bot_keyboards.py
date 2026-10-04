"""Callback data is a wire format between two deploys of the bot.

A button minted today is still sitting in someone's chat tomorrow, so the two
things worth testing are that every payload the keyboards emit parses back to
what built it, and that junk never raises.
"""
import pytest

from app.bot import keyboards
from app.bot.keyboards import MAX_CALLBACK_BYTES, cb, parse_cb
from app.services.education_engine import get_topic, list_topics


def all_buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def every_keyboard():
    """Every keyboard the bot can send, with representative arguments."""
    topic_key = list_topics()[0]["key"]
    return [
        keyboards.main_menu(),
        keyboards.back_to_menu(),
        keyboards.onboarding_prompt(),
        keyboards.goals_menu(),
        keyboards.goal_priority_picker(),
        keyboards.simulate_menu(),
        keyboards.market_menu(["BTC", "ETH", "AAPL"], {"BTC"}),
        keyboards.learn_menu(0),
        keyboards.learn_menu(1),
        keyboards.topic_menu(topic_key),
        keyboards.quiz_options(topic_key, get_topic(topic_key), 0),
        keyboards.quiz_options(topic_key, get_topic(topic_key), 2),
        keyboards.confirm_cancel("goal", "delete", "7"),
        keyboards.skip_keyboard(),
        keyboards.income_type_picker(),
        keyboards.risk_question_options(0, ["a", "b", "c"]),
        keyboards.redo_profile(),
    ]


# --- the convention -----------------------------------------------------

@pytest.mark.parametrize(
    "area,action,arg",
    [
        ("learn", "topic", "risk"),
        ("wl", "add", "BTC"),
        ("goal", "priority", "1"),
        ("menu", "home", None),
        ("quiz", "budgeting", "2"),
    ],
)
def test_callback_data_round_trips(area, action, arg):
    assert parse_cb(cb(area, action, arg)) == (area, action, arg)


@pytest.mark.parametrize("junk", ["", "nonsense", ":", "a:", ":b", None])
def test_junk_parses_to_nothing_instead_of_raising(junk):
    assert parse_cb(junk) == ("", "", None)


def test_an_argument_may_contain_the_separator():
    """Only the first two colons are structural — the rest is the argument."""
    assert parse_cb("learn:topic:a:b") == ("learn", "topic", "a:b")


def test_callback_data_that_would_not_fit_is_refused_at_build_time():
    with pytest.raises(ValueError):
        cb("learn", "topic", "x" * MAX_CALLBACK_BYTES)


# --- every button the bot can send --------------------------------------

@pytest.mark.parametrize("markup", every_keyboard())
def test_every_button_parses_and_fits(markup):
    for button in all_buttons(markup):
        area, action, _ = parse_cb(button.callback_data)
        assert area and action, f"unparseable: {button.callback_data!r}"
        assert len(button.callback_data.encode("utf-8")) <= MAX_CALLBACK_BYTES


@pytest.mark.parametrize("markup", every_keyboard())
def test_every_button_has_a_label(markup):
    assert all(button.text.strip() for button in all_buttons(markup))


# --- the learn menu -----------------------------------------------------

def test_the_learn_menu_paginates_all_twelve_topics():
    seen = set()
    page = 0
    while True:
        buttons = all_buttons(keyboards.learn_menu(page))
        seen |= {parse_cb(b.callback_data)[2] for b in buttons
                 if parse_cb(b.callback_data)[:2] == ("learn", "topic")}
        forward = [b for b in buttons if parse_cb(b.callback_data) == ("learn", "page", str(page + 1))]
        if not forward:
            break
        page += 1

    assert seen == {topic["key"] for topic in list_topics()}


def test_the_first_page_has_no_back_arrow_and_the_last_no_forward():
    first = [parse_cb(b.callback_data) for b in all_buttons(keyboards.learn_menu(0))]
    assert ("learn", "page", "-1") not in first
    assert ("learn", "page", "1") in first

    last = [parse_cb(b.callback_data) for b in all_buttons(keyboards.learn_menu(1))]
    assert ("learn", "page", "2") not in last
    assert ("learn", "page", "0") in last


def test_an_out_of_range_page_clamps_instead_of_emptying():
    assert all_buttons(keyboards.learn_menu(99))
    assert all_buttons(keyboards.learn_menu(-5))


def test_topics_are_laid_out_two_to_a_row():
    rows = keyboards.learn_menu(0).inline_keyboard
    topic_rows = [
        row for row in rows
        if all(parse_cb(b.callback_data)[:2] == ("learn", "topic") for b in row)
    ]
    assert topic_rows and all(len(row) == 2 for row in topic_rows)


# --- the watchlist toggle -----------------------------------------------

def test_the_market_menu_offers_remove_for_watched_and_add_for_the_rest():
    markup = keyboards.market_menu(["BTC", "ETH"], {"BTC"})
    actions = {parse_cb(b.callback_data)[2]: parse_cb(b.callback_data)[1]
               for b in all_buttons(markup) if parse_cb(b.callback_data)[0] == "wl"}

    assert actions == {"BTC": "remove", "ETH": "add"}


# --- the quiz -----------------------------------------------------------

@pytest.mark.parametrize("topic", list_topics(), ids=lambda t: t["key"])
def test_quiz_options_offer_one_button_per_answer(topic):
    for question_idx, question in enumerate(topic["questions"]):
        buttons = [
            b for b in all_buttons(
                keyboards.quiz_options(topic["key"], topic, question_idx))
            if parse_cb(b.callback_data)[0] == "quiz"
        ]

        assert len(buttons) == len(question["options"])
        assert [parse_cb(b.callback_data)[2] for b in buttons] == [
            f"{question_idx}:{i}" for i in range(len(question["options"]))
        ]


@pytest.mark.parametrize("topic", list_topics(), ids=lambda t: t["key"])
def test_quiz_callback_data_fits_telegrams_limit(topic):
    """The payload grew a field. `cb` raises past 64 bytes, so this would
    fail at the longest topic key rather than in somebody's chat."""
    for question_idx in range(len(topic["questions"])):
        keyboards.quiz_options(topic["key"], topic, question_idx)


# --- the command menu ----------------------------------------------------
#
# `messages.COMMAND_HELP` has three consumers: Telegram's own menu, `/help`,
# and the handler table in `bot/main.py`. Nothing registered the menu before,
# so the bot had twelve commands and advertised none of them. These keep the
# table honest now that something depends on it.

def test_every_handler_has_a_description():
    from app.bot import main, messages

    handled = {name for name, _ in main.COMMANDS}
    described = {name for name, _ in messages.COMMAND_HELP}

    assert handled - described == set(), (
        "a command is registered with a handler and has no description, so it "
        "would appear in Telegram's menu with an empty label"
    )


def test_every_description_has_a_handler():
    """A menu entry with nothing behind it is worse than no entry.

    `/help` is the exception: it is a `CommandHandler` built from
    `handlers.help_command` in the same table, so it should be present. If
    this starts failing for a new name, the name was described and never
    wired.
    """
    from app.bot import main, messages

    handled = {name for name, _ in main.COMMANDS}
    described = {name for name, _ in messages.COMMAND_HELP}

    assert described - handled == set()


def test_descriptions_fit_what_a_telegram_client_shows():
    from app.bot import messages

    for name, description in messages.COMMAND_HELP:
        assert description, name
        assert len(description) <= 60, f"/{name}: {len(description)} characters"
        assert description == description.strip(), name
        assert description[0].islower(), f"/{name}: starts upper case"


def test_command_names_are_valid_for_telegram():
    """Lower case, digits and underscores, 1 to 32 characters."""
    import re

    from app.bot import messages

    for name, _ in messages.COMMAND_HELP:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", name), name


def test_no_command_is_listed_twice():
    from app.bot import messages

    names = [name for name, _ in messages.COMMAND_HELP]
    assert len(set(names)) == len(names)


def test_the_help_text_lists_every_command():
    """The help text and the menu are rendered from one table, so this is
    really asserting that the rendering has not been bypassed."""
    from app.bot import messages, views

    text = views.help_view()
    for name, description in messages.COMMAND_HELP:
        assert f"/{name}" in text
        assert description in text


def test_no_em_dash_in_the_command_copy():
    """The project bans em-dashes in user-visible copy, and this copy is
    rendered into a chat and into Telegram's menu."""
    from app.bot import messages, views

    assert "—" not in views.help_view()
    assert not [d for _, d in messages.COMMAND_HELP if "—" in d]
