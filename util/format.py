import traceback
from datetime import timedelta


def nice_duration(seconds: int) -> str:
    units = ["h", "m", "s"]
    formatted = ""
    try:
        t = int(seconds)
    except ValueError:
        return "???"
    else:
        if t == 0:
            return "0s"

        while t >= 1:
            formatted = f" {t % 60}{units.pop()}" + formatted
            t = int(t / 60)
    return formatted.strip()


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
                return f"{s}.000"
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
    v = size
    u = "B"
    while v >= div:
        v /= div
        u = units.pop()
        if u == largest_unit:
            break
    u += "iB" if use_base2 else "B"
    return f"{round(v, decimals if decimals > 0 else None)} {u}"


def ellipsize(s: str, maxlen: int) -> str:
    if len(s) <= maxlen:
        return s
    elif maxlen <= 3:  # too short for ellipses
        return s[:maxlen]
    else:
        if maxlen % 2 == 1:
            return s[0 : int(maxlen / 2 - 1)] + "..." + s[-int(maxlen / 2 - 1) :]
        else:
            return s[0 : int(maxlen / 2 - 1)] + "..." + s[-int(maxlen / 2 - 2) :]
