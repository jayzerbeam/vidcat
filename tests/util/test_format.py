from typing import cast

from util.format import clock_format, ellipsize, nice_bytesize, nice_duration


def test_nice_duration_seconds() -> None:
    assert nice_duration(1) == "1s"


def test_nice_duration_zero() -> None:
    assert nice_duration(0) == "0s"


def test_nice_duration_minutes_rollover() -> None:
    assert nice_duration(60) == "1m 0s"


def test_nice_duration_hours() -> None:
    assert nice_duration(3600) == "1h 0m 0s"


def test_nice_duration_invalid_string() -> None:
    assert nice_duration(cast(int, "x")) == "???"


def test_clock_format_basic() -> None:
    assert clock_format(60) == "01:00"


def test_clock_format_decimals_without_fraction() -> None:
    assert clock_format(60, decimals=2) == "01:00.00"


def test_clock_format_fractional_decimals() -> None:
    assert clock_format(1.2345, decimals=3) == "00:01.234"


def test_clock_format_overflow_returns_none() -> None:
    assert clock_format(1e18) is None


def test_nice_bytesize_bytes() -> None:
    assert nice_bytesize(999) == "999 B"
    assert nice_bytesize(999, use_base2=True) == "999 B"


def test_nice_bytesize_kilobytes() -> None:
    assert nice_bytesize(1000) == "1 KB"


def test_nice_bytesize_base2_with_decimals() -> None:
    assert nice_bytesize(1536, use_base2=True, decimals=1) == "1.5 KiB"


def test_nice_bytesize_largest_unit_cap() -> None:
    assert nice_bytesize(1_000_000, largest_unit="K") == "1000 KB"


def test_ellipsize_short_input_unchanged() -> None:
    assert ellipsize("abc", 5) == "abc"


def test_ellipsize_too_short_for_ellipsis() -> None:
    assert ellipsize("abcdef", 3) == "abc"


def test_ellipsize_odd_maxlen() -> None:
    assert ellipsize("abcdefgh", 5) == "a...h"


def test_ellipsize_even_maxlen() -> None:
    assert ellipsize("abcdefgh", 6) == "ab...h"
