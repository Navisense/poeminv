# Copyright 2023 Navisense GmbH (https://navisense.de)

# This file is part of poeminv.
#
# poeminv is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program, in the file LICENSE at the top level of this
# repository. If not, see <https://www.gnu.org/licenses/>.

import enum
import typing as t
import warnings


def m_to_nm(meters):
    return meters / 1852


class OpDict(dict):
    """
    A dictionary that can be added to and multiplied with others.

    The sum of 2 dictionaries is a new dictionary with a union of all keys.
    Values belonging to keys existing in both dictionaries are added.

    The product of 2 dictionaries is a new dictionary with the keys of the
    left-hand-side operand. Where those keys also exist in the right hand side,
    the result values are the product of both corresponding values.
    """
    def __init__(
            self, *args, start_value_factory: type = int, **kwargs) -> None:
        self._start_value_factory = start_value_factory
        super().__init__(*args, **kwargs)

    def __add__(self, other: dict) -> t.Self:
        return type(self)({
            k: self.get(k, self._start_value_factory())
            + other.get(k, self._start_value_factory())
            for k in set(self) | set(other)})

    def __mul__(self, other: dict) -> t.Self:
        product = {}
        for key, value in self.items():
            try:
                product[key] = value * other[key]
            except KeyError:
                product[key] = value
        return type(self)(product)


class ValueContainsEnumType(enum.EnumType):
    """Enum metaclass that allows containment checks by value."""
    def __contains__(cls, member_or_value):
        # TODO This behavior will become standard in Python 3.12 and this class
        # will no longer be necessary.
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                return super().__contains__(member_or_value)
        except TypeError:
            return any(member.value == member_or_value for member in cls)


class ValueContainsStrEnum(enum.StrEnum, metaclass=ValueContainsEnumType):
    pass


class ValueContainsIntEnum(enum.IntEnum, metaclass=ValueContainsEnumType):
    pass
