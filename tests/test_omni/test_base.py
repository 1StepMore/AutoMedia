"""Tests for BaseOmniAdapter ABC."""

from __future__ import annotations

import pytest

from automedia.omni.base import BaseOmniAdapter


class TestBaseOmniAdapterContract:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseOmniAdapter()  # type: ignore[abstract]

    def test_subclass_without_name_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):

            class _NoName(BaseOmniAdapter):
                def validate_env(self) -> bool:
                    return True

            _NoName()

    def test_subclass_without_validate_env_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):

            class _NoValidateEnv(BaseOmniAdapter):
                @property
                def name(self) -> str:
                    return "bad"

            _NoValidateEnv()
