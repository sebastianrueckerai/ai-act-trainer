import structlog

from app.logging import configure_logging


def test_a_logged_exception_carries_its_traceback(capsys):
    try:
        configure_logging("INFO")
        try:
            raise ZeroDivisionError("division by zero")
        except ZeroDivisionError:
            structlog.get_logger().warning("turn failed", error="boom", exc_info=True)
    finally:
        structlog.reset_defaults()
    rendered = capsys.readouterr().err
    assert '"error": "boom"' in rendered
    assert "Traceback (most recent call last)" in rendered
    assert "ZeroDivisionError: division by zero" in rendered
