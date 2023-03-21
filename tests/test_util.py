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

import poeminv.util as util


class TestOpDict:
    def test_add_both_empty(self):
        d1 = util.OpDict()
        d2 = util.OpDict()
        assert d1 + d2 == {}

    def test_add_one_empty(self):
        d1 = util.OpDict({'a': 1, 'b': 2})
        d2 = util.OpDict()
        assert d1 + d2 == {'a': 1, 'b': 2}

    def test_add_same_keys(self):
        d1 = util.OpDict({'a': 1, 'b': 2})
        d2 = util.OpDict({'a': 4, 'b': 8})
        assert d1 + d2 == {'a': 5, 'b': 10}

    def test_add_disjoint_keys(self):
        d1 = util.OpDict({'a': 1, 'b': 2})
        d2 = util.OpDict({'c': 4, 'd': 8})
        assert d1 + d2 == {'a': 1, 'b': 2, 'c': 4, 'd': 8}

    def test_add_overlapping_keys(self):
        d1 = util.OpDict({'a': 1, 'b': 2})
        d2 = util.OpDict({'b': 4, 'c': 8})
        assert d1 + d2 == {'a': 1, 'b': 6, 'c': 8}

    def test_add_results_are_summable_again(self):
        d1 = util.OpDict({'a': 1})
        d2 = util.OpDict({'b': 2})
        d3 = util.OpDict({'a': 4})
        d4 = util.OpDict({'b': 8})
        result = d1 + d2
        result = result + d3
        result = result + d4
        assert result == {'a': 5, 'b': 10}

    def test_add_custom_start_value(self):
        d1 = util.OpDict(
            {'a': util.OpDict({'x': 1, 'y': 2}), 'b': util.OpDict({'y': 4})},
            start_value_factory=util.OpDict)
        d2 = util.OpDict(
            {'a': util.OpDict({'y': 8}), 'c': util.OpDict({'z': 16})},
            start_value_factory=util.OpDict)
        assert d1 + d2 == {
            'a': {'x': 1, 'y': 10}, 'b': {'y': 4}, 'c': {'z': 16}}

    def test_add_result_is_same_type(self):
        class SD2(util.OpDict):
            pass

        d1 = SD2({'a': 1})
        d2 = SD2({'a': 4})
        assert isinstance(d1 + d2, SD2)

    def test_mul_both_empty(self):
        assert util.OpDict() * {} == {}

    def test_mul_left_empty(self):
        assert util.OpDict() * {'a': 1} == {}

    def test_mul_right_empty(self):
        assert util.OpDict({'a': 1}) * {} == {'a': 1}

    def test_mul_same_keys(self):
        d1 = util.OpDict({'a': 2, 'b': 3})
        d2 = {'a': 5, 'b': 7}
        assert d1 * d2 == {'a': 10, 'b': 21}

    def test_mul_disjoint_keys(self):
        d1 = util.OpDict({'a': 1, 'b': 2})
        d2 = {'c': 4, 'd': 8}
        assert d1 * d2 == {'a': 1, 'b': 2}

    def test_mul_overlapping_keys(self):
        d1 = util.OpDict({'a': 2, 'b': 3})
        d2 = {'b': 5, 'c': 7}
        assert d1 * d2 == {'a': 2, 'b': 15}

    def test_mul_results_are_multipliable_again(self):
        d1 = util.OpDict({'a': 2, 'b': 3})
        d2 = {'a': 5}
        d3 = {'b': 7}
        d4 = {'a': 11}
        assert d1 * d2 * d3 * d4 == {'a': 110, 'b': 21}

    def test_mul_result_is_same_type(self):
        class SD2(util.OpDict):
            pass

        assert isinstance(SD2({'a': 1}) * {'a': 4}, SD2)
