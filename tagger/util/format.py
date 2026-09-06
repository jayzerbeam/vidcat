from datetime import timedelta


def nice_duration(seconds: int) -> str:
    units = ["h", "m", "s"]
    formatted = ""
    try:
        t = int(seconds)
    except ValueError:
        return "???"
    else:
        while t >= 1:
            formatted = f" {t % 60}{units.pop()}" + formatted
            t = int(t / 60)
    return formatted.strip()


def clock_format(seconds: float, with_decimal: bool = False) -> str:
    s = str(timedelta(seconds=seconds)).removeprefix("0:")
    if not with_decimal:
        s = s.split(".")[0]
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
