from typing import cast

import pytest

from util.format import clock_format, ellipsize, nice_bytesize, nice_duration


def test_nice_duration_seconds() -> None:
    assert nice_duration(1) == "1s"


def test_nice_duration_zero() -> None:
    assert nice_duration(0) == "0s"


def test_nice_duration_minutes_rollover() -> None:
    assert nice_duration(60) == "1m 0s"


def test_nice_duration_hours() -> None:
    assert nice_duration(3600) == "1h 0m 0s"


def test_nice_duration_sixty_plus_hours() -> None:
    assert nice_duration(216000) == "60h 0m 0s"
    assert nice_duration(259261) == "72h 1m 1s"


def test_nice_duration_float_seconds() -> None:
    assert nice_duration(0.5) == "0s"
    assert nice_duration(61.9) == "1m 1s"


def test_nice_duration_negative() -> None:
    assert nice_duration(-0.5) == "0s"
    assert nice_duration(-1) == "-1s"
    assert nice_duration(-65) == "-1m 5s"
    assert nice_duration(-3600) == "-1h 0m 0s"
    assert nice_duration(-216000) == "-60h 0m 0s"


def test_nice_duration_invalid_string() -> None:
    assert nice_duration(cast(int, "x")) == "???"


def test_nice_duration_none_and_non_finite() -> None:
    assert nice_duration(cast(int, None)) == "???"
    assert nice_duration(float("inf")) == "???"
    assert nice_duration(float("nan")) == "???"


def test_clock_format_basic() -> None:
    assert clock_format(60) == "1:00"


def test_clock_format_sub_minute() -> None:
    assert clock_format(5) == "0:05"
    assert clock_format(0.5, decimals=3) == "0:00.500"


def test_clock_format_decimals_without_fraction() -> None:
    assert clock_format(60, decimals=2) == "1:00.00"


def test_clock_format_fractional_decimals() -> None:
    assert clock_format(1.2345, decimals=3) == "0:01.234"


def test_clock_format_inf_returns_none() -> None:
    assert clock_format(float("inf")) is None
    assert clock_format(float("-inf")) is None


def test_clock_format_nan_returns_none() -> None:
    assert clock_format(float("nan")) is None


def test_clock_format_huge_finite_value_renders() -> None:
    assert clock_format(10**15) == "277777777777:46:40"


def test_clock_format_float_strips_microseconds() -> None:
    # FMT-03: durations like round(125.43, 2) used to render "02:05.430000"
    assert clock_format(125.43) == "2:05"
    assert clock_format(59.5) == "0:59"


def test_clock_format_hours_not_padded() -> None:
    assert clock_format(3600) == "1:00:00"
    assert clock_format(3599) == "59:59"


def test_clock_format_beyond_24_hours_stays_a_clock_string() -> None:
    # FMT-04: timedelta's "N day(s), ..." form is not a clock string
    assert clock_format(86_400) == "24:00:00"
    assert clock_format(90_061) == "25:01:01"


def test_clock_format_fraction_truncated_to_decimals() -> None:
    assert clock_format(125.43, decimals=1) == "2:05.4"
    assert clock_format(125.43, decimals=3) == "2:05.430"


def test_clock_format_hours_with_fraction() -> None:
    assert clock_format(3661.5, decimals=3) == "1:01:01.500"


def test_clock_format_negative() -> None:
    assert clock_format(-5) == "-0:05"


def test_clock_format_omit_zero_false_pads_all_fields() -> None:
    assert clock_format(5, omit_zero=False) == "00:00:05"
    assert clock_format(65, omit_zero=False) == "00:01:05"
    assert clock_format(3600, omit_zero=False) == "01:00:00"
    assert clock_format(90_061, omit_zero=False) == "25:01:01"


def test_nice_bytesize_bytes() -> None:
    assert nice_bytesize(999) == "999 B"
    assert nice_bytesize(999, use_base2=True) == "999 B"


def test_nice_bytesize_kilobytes() -> None:
    assert nice_bytesize(1000) == "1 KB"


def test_nice_bytesize_base2_with_decimals() -> None:
    assert nice_bytesize(1536, use_base2=True, decimals=1) == "1.5 KiB"


def test_nice_bytesize_largest_unit_cap() -> None:
    assert nice_bytesize(1_000_000, largest_unit="K") == "1000 KB"


def test_nice_bytesize_invalid_largest_unit() -> None:
    with pytest.raises(ValueError):
        nice_bytesize(10**30, largest_unit="Z")


def test_ellipsize_short_input_unchanged() -> None:
    assert ellipsize("abc", 5) == "abc"


def test_ellipsize_too_short_for_ellipsis() -> None:
    assert ellipsize("abcdef", 3) == "abc"


def test_ellipsize_min_ellipsis_length() -> None:
    result = ellipsize("abcdefgh", 4)
    assert result == "a..."
    assert len(result) <= 4


def test_ellipsize_odd_maxlen() -> None:
    assert ellipsize("abcdefgh", 5) == "a...h"


def test_ellipsize_even_maxlen() -> None:
    assert ellipsize("abcdefgh", 6) == "ab...h"
