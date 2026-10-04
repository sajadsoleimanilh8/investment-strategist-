"""Outbound email.

One interface, two transports, chosen by `MAIL_TRANSPORT`.

`console` writes the message to the log instead of sending it, and it is the
default for the same reason `DEMO_MODE` exists: the whole product has to run
with nothing external reachable, and a password reset that cannot complete
offline would be the first thing to break that. The reset link is printed in
full, so a developer or a demo can follow it.

`smtp` is stdlib `smtplib` over TLS. No dependency, no API key, and nothing
about it is verified here — the same posture as the market providers. It needs
a real server to prove, which makes it a pre-deploy check rather than a test.

What neither transport does is tell the caller whether a person received
anything. `/api/auth/forgot-password` answers 202 either way on purpose (see
the route), so a send failure is logged and swallowed rather than turned into
a response that reveals whether an address is registered.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from app.core.config import settings
from app.core.logging import UNSCRUBBED

log = logging.getLogger("finmentor.mail")


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    def send(self, message: Message) -> None:
        ...


class ConsoleMailer:
    """Logs the message. The offline default.

    The body is logged in full, including the reset link, which is the point:
    without a transport this is the only way to complete the flow. That is
    also why it must never be the transport in production, and why
    `check_production` refuses to start on it outside DEMO_MODE.
    """

    name = "console"

    def send(self, message: Message) -> None:
        # `UNSCRUBBED` because the formatter masks credentials in log
        # output, and the reset link in this body is exactly such a
        # credential. It is also the only way to finish the flow without a
        # mail transport, which is this class's whole reason to exist.
        # `check_production` refuses to start on this transport outside
        # DEMO_MODE, and that guard is what makes the exemption safe. It is
        # the only one in the codebase, and a test keeps it that way.
        log.info(
            "email not sent (console transport)\nTo: %s\nSubject: %s\n\n%s",
            message.to, message.subject, message.body,
            extra={UNSCRUBBED: True},
        )


class SmtpMailer:
    """A real send over STARTTLS.

    Untested against a live server from this machine, exactly like the market
    providers: what is unverified is whether the host, port and credentials
    are right, not whether this code composes a message.
    """

    name = "smtp"

    def send(self, message: Message) -> None:
        email = EmailMessage()
        email["From"] = settings.mail_from
        email["To"] = message.to
        email["Subject"] = message.subject
        email.set_content(message.body)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(email)


def build_mailer() -> Mailer:
    if settings.mail_transport == "smtp":
        return SmtpMailer()
    return ConsoleMailer()


def send_quietly(message: Message) -> None:
    """Send, and log rather than raise if the transport fails.

    Every caller is a route that must answer the same way whether or not the
    address exists. An exception here would turn a mail outage into a 500 on
    a request that otherwise succeeded, and a 500 on one address and a 202 on
    another is an account-existence oracle with extra steps.
    """
    try:
        build_mailer().send(message)
    except Exception as exc:                      # transport down, bad credentials
        log.warning("could not send %r to a user: %s", message.subject, exc)
