import utils


class TestOpDict:
    def test_add_both_empty(self):
        d1 = utils.OpDict()
        d2 = utils.OpDict()
        assert d1 + d2 == {}

    def test_add_one_empty(self):
        d1 = utils.OpDict({'a': 1, 'b': 2})
        d2 = utils.OpDict()
        assert d1 + d2 == {'a': 1, 'b': 2}

    def test_add_same_keys(self):
        d1 = utils.OpDict({'a': 1, 'b': 2})
        d2 = utils.OpDict({'a': 4, 'b': 8})
        assert d1 + d2 == {'a': 5, 'b': 10}

    def test_add_disjoint_keys(self):
        d1 = utils.OpDict({'a': 1, 'b': 2})
        d2 = utils.OpDict({'c': 4, 'd': 8})
        assert d1 + d2 == {'a': 1, 'b': 2, 'c': 4, 'd': 8}

    def test_add_overlapping_keys(self):
        d1 = utils.OpDict({'a': 1, 'b': 2})
        d2 = utils.OpDict({'b': 4, 'c': 8})
        assert d1 + d2 == {'a': 1, 'b': 6, 'c': 8}

    def test_add_results_are_summable_again(self):
        d1 = utils.OpDict({'a': 1})
        d2 = utils.OpDict({'b': 2})
        d3 = utils.OpDict({'a': 4})
        d4 = utils.OpDict({'b': 8})
        result = d1 + d2
        result = result + d3
        result = result + d4
        assert result == {'a': 5, 'b': 10}

    def test_add_custom_start_value(self):
        d1 = utils.OpDict(
            {'a': utils.OpDict({'x': 1, 'y': 2}), 'b': utils.OpDict({'y': 4})},
            start_value_factory=utils.OpDict)
        d2 = utils.OpDict(
            {'a': utils.OpDict({'y': 8}), 'c': utils.OpDict({'z': 16})},
            start_value_factory=utils.OpDict)
        assert d1 + d2 == {
            'a': {'x': 1, 'y': 10}, 'b': {'y': 4}, 'c': {'z': 16}}

    def test_add_result_is_same_type(self):
        class SD2(utils.OpDict):
            pass

        d1 = SD2({'a': 1})
        d2 = SD2({'a': 4})
        assert isinstance(d1 + d2, SD2)

    def test_mul_both_empty(self):
        assert utils.OpDict() * {} == {}

    def test_mul_left_empty(self):
        assert utils.OpDict() * {'a': 1} == {}

    def test_mul_right_empty(self):
        assert utils.OpDict({'a': 1}) * {} == {'a': 1}

    def test_mul_same_keys(self):
        d1 = utils.OpDict({'a': 2, 'b': 3})
        d2 = {'a': 5, 'b': 7}
        assert d1 * d2 == {'a': 10, 'b': 21}

    def test_mul_disjoint_keys(self):
        d1 = utils.OpDict({'a': 1, 'b': 2})
        d2 = {'c': 4, 'd': 8}
        assert d1 * d2 == {'a': 1, 'b': 2}

    def test_mul_overlapping_keys(self):
        d1 = utils.OpDict({'a': 2, 'b': 3})
        d2 = {'b': 5, 'c': 7}
        assert d1 * d2 == {'a': 2, 'b': 15}

    def test_mul_results_are_multipliable_again(self):
        d1 = utils.OpDict({'a': 2, 'b': 3})
        d2 = {'a': 5}
        d3 = {'b': 7}
        d4 = {'a': 11}
        assert d1 * d2 * d3 * d4 == {'a': 110, 'b': 21}

    def test_mul_result_is_same_type(self):
        class SD2(utils.OpDict):
            pass

        assert isinstance(SD2({'a': 1}) * {'a': 4}, SD2)