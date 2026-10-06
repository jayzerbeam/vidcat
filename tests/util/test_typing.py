from typing import cast

import pytest

from util.typing import enforce_types, param_types


def test_enforce_types_positional() -> None:
    @enforce_types
    def add(a: int, b: int) -> int:
        return a + b

    assert add(1, 2) == 3


def test_enforce_types_rejects_wrong_positional() -> None:
    @enforce_types
    def add(a: int, b: int) -> int:
        return a + b

    with pytest.raises(TypeError, match="parameter 'a'"):
        add(cast(int, "x"), 2)


def test_enforce_types_rejects_wrong_keyword() -> None:
    @enforce_types
    def greet(name: str) -> str:
        return f"hi {name}"

    with pytest.raises(TypeError, match="named parameter 'name'"):
        greet(name=cast(str, 5))


def test_enforce_types_skips_unannotated() -> None:
    @enforce_types
    def ident(a, b: int):
        return a, b

    assert ident("x", 1) == ("x", 1)


def test_enforce_types_callable_keyword() -> None:
    @enforce_types
    def run(cb: callable) -> str:  # pyright: ignore[reportGeneralTypeIssues]
        return cb()

    assert run(cb=lambda: "ok") == "ok"
    with pytest.raises(TypeError, match="named parameter 'cb'"):
        run(cb=5)


def test_param_types_deprecated_and_checked() -> None:
    with pytest.warns(DeprecationWarning):

        @param_types(int)
        def ident(a):
            return a

    with pytest.raises(TypeError):
        ident(cast(int, "x"))
