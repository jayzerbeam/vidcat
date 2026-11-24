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


def clock_format(seconds: float, decimals: int = 0, omit_zero: bool = True) -> str | None:
    """returns seconds as a string in the format HH:MM:SS.DDD

    omit_zero only affects HH and MM
    length of D is specified by decimals
    returns None if not finite"""
    try:
        micros = round(seconds * 1_000_000)
    except OverflowError, ValueError:  # inf and nan
        return None
    sign = "-" if micros < 0 else ""
    whole, micro = divmod(abs(micros), 1_000_000)
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    if omit_zero and hours == 0:
        clock = f"{minutes}:{secs:02d}"
    elif omit_zero:
        clock = f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        clock = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    if decimals > 0:
        fraction = f"{micro:06d}"[:decimals]
        clock = f"{clock}.{fraction}"
    return f"{sign}{clock}"


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
