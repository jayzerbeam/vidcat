import traceback
from datetime import timedelta


def nice_duration(seconds: float) -> str:
    units = ["h", "m", "s"]
    formatted = ""
    try:
        t = int(seconds)
    except ValueError, TypeError, OverflowError:
        return "???"
    else:
        if t == 0:
            return "0s"

        sign = "-" if t < 0 else ""
        t = abs(t)
        while t >= 1:
            unit = units.pop()
            if units:
                t, val = divmod(t, 60)
            else:
                t, val = 0, t
            formatted = f" {val}{unit}" + formatted
    return f"{sign}{formatted.strip()}"


def clock_format(seconds: float, decimals: int = 0) -> str | None:
    try:
        s = str(timedelta(seconds=seconds)).removeprefix("0:")
    except OverflowError:
        traceback.print_exc()
        return None
    else:
        if decimals > 0:
            sp = s.split(".")
            if len(sp) > 1:
                return f"{sp[0]}.{sp[1][:decimals]}"
            else:
                return f"{s}.{'0' * decimals}"
        else:
            return s


def nice_bytesize(size: int, largest_unit: str = "E", use_base2: bool = False, decimals: int = 0) -> str:
    """Return a size formatted string

    paramters:
    size (int): in bytes
    largest_unit (str): K M G T P E
    use_base2 (bool): 1024 divisor for units
    decimals (int): decimal places
    """

    div = 1024 if use_base2 else 1000
    units = list("EPTGMK")
    if largest_unit not in units:
        raise ValueError(f"invalid largest_unit ({largest_unit})")

    v = size
    u = ""
    while v >= div:
        v /= div
        u = units.pop()
        if u == largest_unit:
            break
    u += "iB" if u and use_base2 else "B"
    return f"{round(v, decimals if decimals > 0 else None)} {u}"


def ellipsize(s: str, maxlen: int) -> str:
    if len(s) <= maxlen:
        return s
    elif maxlen <= 3:  # too short for ellipses
        return s[:maxlen]
    else:
        head = int(maxlen / 2 - 1)
        tail = maxlen - head - 3
        return s[:head] + "..." + (s[-tail:] if tail > 0 else "")
