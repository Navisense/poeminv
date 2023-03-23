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

import dataclasses as dc
import itertools as it

from hamcrest import *
import pytest

import poeminv.config as cfg
import poeminv.event as ev


def low_load_adjustment_factors(*range_factors):
    return contains_exactly(
        *[
            contains_exactly(
                all_of(instance_of(cfg.Range), has_properties(_ge=ge, _lt=lt)),
                factors) for ge, lt, factors in range_factors])


@pytest.fixture
def make_vessel_info_attrs():
    import numbers
    value_counter = it.count(1)
    engine_categories = it.cycle(cfg.EngineCategory)
    ship_types = it.cycle(cfg.VALID_SHIP_TYPE_SIZE_UNITS)
    engine_nox_tiers = it.cycle(cfg.EngineNOxTier)

    def factory(*, only_attrs=None, **kwargs):
        attrs = {}
        for field in dc.fields(cfg.VesselInfo):
            if ((only_attrs and field.name not in only_attrs)
                    or field.name == 'size_unit'):
                continue
            if field.name == 'engine_category':
                attrs[field.name] = next(engine_categories)
            elif field.name == 'ship_type':
                ship_type = kwargs.get('ship_type') or next(ship_types)
                attrs[field.name] = ship_type
                if ('size_unit' not in kwargs
                        and (not only_attrs or 'size_unit' in only_attrs)):
                    attrs['size_unit'] = (
                        cfg.VALID_SHIP_TYPE_SIZE_UNITS[ship_type][0])
            elif field.name == 'engine_nox_tier':
                attrs[field.name] = next(engine_nox_tiers)
            elif issubclass(field.type, str):
                attrs[field.name] = f'{field.name}_{next(value_counter)}'
            else:
                assert issubclass(field.type, numbers.Number)
                attrs[field.name] = next(value_counter)
        return attrs | kwargs

    return factory


class TestRange:
    def test_matches_lower_bound(self):
        assert 5 in cfg.Range(5, 25)

    def test_matches_inside(self):
        assert 15 in cfg.Range(5, 25)

    def test_doesnt_match_below(self):
        assert 4 not in cfg.Range(5, 25)

    def test_doesnt_match_upper_bound(self):
        assert 25 not in cfg.Range(5, 25)

    def test_doesnt_match_above(self):
        assert 30 not in cfg.Range(5, 25)


class TestCriterion:
    class C(cfg.Criterion):
        def _value_fulfills(self, predicate):
            return predicate(5)

        def matches(self, **values):
            return True

    def test_init_raises_with_invalid_name(self):
        with pytest.raises(ValueError):
            self.C('not_a_valid_name')

    def test_can_register_new_names_as_valid(self):
        cfg.Criterion.register_name('suddenly_a_valid_name')
        self.C('suddenly_a_valid_name')

    def test_init_raises_if_value_doesnt_pass_validation(self):
        cfg.Criterion.register_name('less_than_10', lambda x: x < 10)
        cfg.Criterion.register_name('less_than_3', lambda x: x < 3)
        self.C('less_than_10')
        with pytest.raises(ValueError):
            self.C('less_than_3')


class TestEqualsCriterion:
    def test_matches_equal(self):
        criterion = cfg.EqualsCriterion('length', 5)
        assert criterion.matches(length=5, b=6)

    def test_doesnt_match_unequal(self):
        criterion = cfg.EqualsCriterion('length', 5)
        assert not criterion.matches(length=6, b=5)

    def test_doesnt_match_nonexistent(self):
        criterion = cfg.EqualsCriterion('length', 5)
        assert not criterion.matches(b=5)


class TestRangeCriterion:
    def test_matches_lower_bound(self):
        criterion = cfg.RangeCriterion('length', 5, 25)
        assert criterion.matches(length=5, b=30)

    def test_matches_inside(self):
        criterion = cfg.RangeCriterion('length', 5, 25)
        assert criterion.matches(length=15, b=30)

    def test_doesnt_match_below(self):
        criterion = cfg.RangeCriterion('length', 5, 25)
        assert not criterion.matches(length=4, b=15)

    def test_doesnt_match_upper_bound(self):
        criterion = cfg.RangeCriterion('length', 5, 25)
        assert not criterion.matches(length=25, b=15)

    def test_doesnt_match_above(self):
        criterion = cfg.RangeCriterion('length', 5, 25)
        assert not criterion.matches(length=30, b=15)

    def test_doesnt_match_nonexistent(self):
        criterion = cfg.RangeCriterion('length', 5, 25)
        assert not criterion.matches(b=15)

    def test_doesnt_match_non_numbers(self):
        criterion = cfg.RangeCriterion('length', 5, 25)
        assert not criterion.matches(length='x')
        assert not criterion.matches(length=None)


class TestDisjunctionCriterion:
    def range(self, lower_bound, upper_bound):
        return cfg.RangeCriterion('length', lower_bound, upper_bound)

    def test_doesnt_match_without_criteria(self):
        criterion = cfg.DisjunctionCriterion('length')
        assert not criterion.matches()
        assert not criterion.matches(length=5)

    def test_matches_if_only_criterion_matches(self):
        criterion = cfg.DisjunctionCriterion('length', self.range(5, 6))
        assert criterion.matches(length=5)

    def test_matches_if_all_criteria_match(self):
        criterion = cfg.DisjunctionCriterion(
            'length', self.range(0, 10), self.range(3, 7), self.range(5, 6))
        assert criterion.matches(length=5)

    def test_matches_if_one_criterion_matches(self):
        criterion = cfg.DisjunctionCriterion(
            'length', self.range(0, 10), self.range(3, 7), self.range(20, 25))
        assert criterion.matches(length=21)

    def test_doesnt_match_if_no_criterion_matches(self):
        criterion = cfg.DisjunctionCriterion(
            'length', self.range(0, 10), self.range(3, 7))
        assert not criterion.matches(length=10)

    def test_doesnt_match_nonexistent(self):
        criterion = cfg.DisjunctionCriterion('length', self.range(0, 10))
        assert not criterion.matches()
        assert not criterion.matches(b=5)


class TestMatchConfig:
    def test_extracts_data(self):
        match_config = cfg.MatchConfig({
            'match_criteria': {}, 'x': 1, 'y': 'asd'})
        assert match_config.data == {'x': 1, 'y': 'asd'}

    def test_parses_empty_criteria(self):
        match_config = cfg.MatchConfig({'match_criteria': {}})
        assert match_config.matches()
        assert match_config.matches(a=1)

    def test_parses_criteria(self):
        match_config = cfg.MatchConfig({
            'match_criteria': {
                'ship_type': 'tug', 'length': {'ge': 5, 'lt': 25},
                'width': {'any_of': [1, {'ge': 3, 'lt': 6}]}}, 'x': 1})
        assert match_config.matches(ship_type='tug', length=15, width=1)
        assert match_config.matches(ship_type='tug', length=15, width=3)
        assert not match_config.matches(ship_type='asdf', length=15, width=1)
        assert not match_config.matches(ship_type='tug', length=30, width=1)
        assert not match_config.matches(ship_type='tug', length=15, width=2)
        assert not match_config.matches(ship_type='asdf', length=30, width=10)


class TestEmissionConfig:
    def test_calculate_emissions_for_energy(self):
        config = cfg.EmissionConfig({
            'propulsion': {'p1': 2, 'p2': 4}, 'auxiliary': {'p2': 8},
            'boiler': {}}, {'auxiliary': 0, 'boiler': 0}, [])
        actual_propulsion = config.emissions_from_energy('propulsion', 1.5)
        actual_auxiliary = config.emissions_from_energy('auxiliary', 1.5)
        actual_boiler = config.emissions_from_energy('boiler', 1.5)
        assert actual_propulsion == {'p1': 3, 'p2': 6}
        assert actual_auxiliary == {'p2': 12}
        assert actual_boiler == {}

    def test_engine_power(self):
        config = cfg.EmissionConfig(
            {'propulsion': {}, 'auxiliary': {}, 'boiler': {}},
            {'auxiliary': 7, 'boiler': 8}, [])
        assert config.engine_power('auxiliary') == 7
        assert config.engine_power('boiler') == 8


class TestEmissionConfigs:
    def make_configs(
            self, *, base_values=None, pollutants=None, engine_powers=None,
            low_load_adjustment_factors=None):
        base_values = base_values or []
        pollutants = pollutants or []
        llaf = low_load_adjustment_factors or []
        engine_powers = engine_powers or [({'engine_group': 'auxiliary'}, {}),
                                          ({'engine_group': 'boiler'}, {})]
        base_values_configs, pollutants_configs, llaf_configs = {}, {}, []
        engine_powers_configs = []
        for name, specs in base_values:
            for match_criteria, g_per_kwh in specs:
                base_values_configs.setdefault(name, []).append(
                    cfg.MatchConfig({
                        'match_criteria': match_criteria,
                        'g_per_kwh': g_per_kwh}))
        for name, specs in pollutants:
            for spec in specs:
                if len(spec) == 2:
                    match_criteria, b = spec
                    multiplier, offset = None, None
                else:
                    match_criteria, b, multiplier, offset = spec
                config_dict = {
                    'match_criteria': match_criteria, 'base_value_name': b}
                if multiplier is not None:
                    config_dict['multiplier'] = multiplier
                if offset is not None:
                    config_dict['offset_g_per_kwh'] = offset
                pollutants_configs.setdefault(name, []).append(
                    cfg.MatchConfig(config_dict))
        for match_criteria, engine_power in engine_powers:
            engine_power = {
                ev.Mode.TRANSIT: 1, ev.Mode.MANEUVERING: 2,
                ev.Mode.HOTELLING: 3, ev.Mode.ANCHORAGE: 4} | engine_power
            engine_powers_configs.append(
                cfg.MatchConfig({'match_criteria': match_criteria}
                                | engine_power))
        for match_criteria, range_factors in llaf:
            rfs = [{'range': {'ge': ge, 'lt': lt}, 'factors': factors}
                   for ge, lt, factors in range_factors]
            llaf_configs.append(
                cfg.MatchConfig({
                    'match_criteria': match_criteria, 'range_factors': rfs}))
        return cfg.EmissionConfigs(
            base_values_configs, pollutants_configs, engine_powers_configs,
            llaf_configs)

    @pytest.fixture
    def make_vessel_info(self, make_vessel_info_attrs):
        def factory(**kwargs):
            return cfg.VesselInfo(**make_vessel_info_attrs(**kwargs))

        return factory

    def test_returns_config_without_criteria(self, make_vessel_info):
        configs = self.make_configs(
            base_values=[(
                'b1', [({'engine_group': 'propulsion'}, 2),
                       ({'engine_group': 'auxiliary'}, 4)]),
                         ('b2', [({'engine_group': 'auxiliary'}, 8)])],
            pollutants=[(
                'p1', [({'engine_group': 'propulsion'}, 'b1'),
                       ({'engine_group': 'auxiliary'}, 'b1')]),
                        ('p2', [({'engine_group': 'auxiliary'}, 'b2')])],
        )
        emission_config = configs.config_for(
            make_vessel_info(), ev.Mode.TRANSIT)
        actual_propulsion = emission_config.emissions_from_energy(
            'propulsion', 1.5)
        actual_auxiliary = emission_config.emissions_from_energy(
            'auxiliary', 1.5)
        assert actual_propulsion == {'p1': 3}
        assert actual_auxiliary == {'p1': 6, 'p2': 12}

    @pytest.mark.parametrize('engine_group', ['propulsion', 'auxiliary'])
    def test_returns_config_with_criteria(
            self, make_vessel_info, engine_group):
        configs = self.make_configs(
            base_values=[
                (
                    'b1', [({
                        'engine_group': engine_group,
                        'engine_rpm': {'ge': 0, 'lt': 1500}}, 2),
                           ({'engine_group': engine_group}, 4)]),
                (
                    'b2', [({
                        'engine_group': engine_group,
                        'engine_rpm': {'ge': 1500, 'lt': 2500}}, 8),
                           ({'engine_group': engine_group}, 16)]),],
            pollutants=[(
                'p1', [({
                    'engine_group': engine_group,
                    'engine_rpm': {'ge': 0, 'lt': 1000}}, 'b1'),
                       ({'engine_group': engine_group}, 'b2')])],
        )
        p1b1_config = configs.config_for(
            make_vessel_info(engine_rpm=800), ev.Mode.TRANSIT)
        assert_that(
            p1b1_config.emissions_from_energy(engine_group, 1.5),
            has_entries(p1=3))
        p1b2_config = configs.config_for(
            make_vessel_info(engine_rpm=1200), ev.Mode.TRANSIT)
        assert_that(
            p1b2_config.emissions_from_energy(engine_group, 1.5),
            has_entries(p1=24))
        non_matching_config = configs.config_for(
            make_vessel_info(engine_rpm=1700), ev.Mode.TRANSIT)
        assert_that(
            non_matching_config.emissions_from_energy(engine_group, 1.5),
            has_entries(p1=12))

    def test_returns_first_matching_config(self, make_vessel_info):
        configs = self.make_configs(
            base_values=[(
                'b1', [({'engine_group': 'propulsion'}, 4),
                       ({'engine_group': 'propulsion'}, 2),
                       ({'engine_group': 'propulsion'}, 8)])],
            pollutants=[('p1', [({'engine_group': 'propulsion'}, 'b1')])],
        )
        emission_config = configs.config_for(
            make_vessel_info(), ev.Mode.TRANSIT)
        actual = emission_config.emissions_from_energy('propulsion', 1.5)
        assert actual == {'p1': 6}

    def test_combines_multiplier(self, make_vessel_info):
        configs = self.make_configs(
            base_values=[('b1', [({'engine_group': 'propulsion'}, 2)])],
            pollutants=[
                ('p1', [({'engine_group': 'propulsion'}, 'b1', 1.5, None)])],
        )
        emission_config = configs.config_for(
            make_vessel_info(), ev.Mode.TRANSIT)
        actual = emission_config.emissions_from_energy('propulsion', 3)
        assert actual == {'p1': 9}

    def test_combines_offset(self, make_vessel_info):
        configs = self.make_configs(
            base_values=[('b1', [({'engine_group': 'propulsion'}, 2)])],
            pollutants=[
                ('p1', [({'engine_group': 'propulsion'}, 'b1', None, 0.5)])],
        )
        emission_config = configs.config_for(
            make_vessel_info(), ev.Mode.TRANSIT)
        actual = emission_config.emissions_from_energy('propulsion', 3)
        assert actual == {'p1': 7.5}

    def test_combines_offset_and_multiplier(self, make_vessel_info):
        configs = self.make_configs(
            base_values=[('b1', [({'engine_group': 'propulsion'}, 2)])],
            pollutants=[
                ('p1', [({'engine_group': 'propulsion'}, 'b1', 1.5, 5)])],
        )
        emission_config = configs.config_for(
            make_vessel_info(), ev.Mode.TRANSIT)
        actual = emission_config.emissions_from_energy('propulsion', 3)
        assert actual == {'p1': 24}

    def test_returns_config_without_criteria_first(self, make_vessel_info):
        configs = self.make_configs(
            base_values=[
                ('b1', [({}, 4), ({'engine_group': 'propulsion'}, 2)])],
            pollutants=[('p1', [({'engine_group': 'propulsion'}, 'b1')])],
        )
        emission_config = configs.config_for(
            make_vessel_info(), ev.Mode.TRANSIT)
        actual = emission_config.emissions_from_energy('propulsion', 1.5)
        assert actual == {'p1': 6}

    def test_checks_criteria_for_base_value_and_pollutant(
            self, make_vessel_info):
        configs = self.make_configs(
            base_values=[
                ('b1', [({}, 4), ({'engine_group': 'propulsion'}, 2)]),
                ('b2', [({'engine_group': 'propulsion'}, 8)])],
            pollutants=[
                ('p1', [({'engine_group': 'auxiliary'}, 'b1'), ({}, 'b2')])],
        )
        emission_config = configs.config_for(
            make_vessel_info(), ev.Mode.TRANSIT)
        actual = emission_config.emissions_from_energy('propulsion', 1.5)
        assert actual == {'p1': 12}

    def test_returns_empty_without_configs(self, make_vessel_info):
        configs = self.make_configs()
        emission_config = configs.config_for(
            make_vessel_info(), ev.Mode.TRANSIT)
        assert emission_config.emissions_from_energy('propulsion', 3) == {}

    def test_returns_empty_without_matching_configs(self, make_vessel_info):
        configs = self.make_configs(
            base_values=[('b1', [({'engine_group': 'auxiliary'}, 2)])],
            pollutants=[('p1', [({'engine_group': 'auxiliary'}, 'b1')])],
        )
        emission_config = configs.config_for(
            make_vessel_info(), ev.Mode.TRANSIT)
        assert emission_config.emissions_from_energy('propulsion', 3) == {}

    @pytest.mark.parametrize('mode', list(ev.Mode))
    def test_returns_engine_powers(self, make_vessel_info, mode):
        configs = self.make_configs(
            engine_powers=[(
                {'engine_group': 'auxiliary'},
                {mode: 1234}), ({'engine_group': 'boiler'}, {mode: 2345})])
        emission_config = configs.config_for(make_vessel_info(), mode)
        assert emission_config.engine_power('auxiliary') == 1234
        assert emission_config.engine_power('boiler') == 2345

    def test_returns_matching_adjustment_factors(self, make_vessel_info):
        configs = self.make_configs(
            low_load_adjustment_factors=[
                ({'engine_rpm': 400}, [(0, 10, {'p1': 2})]),
                ({'engine_rpm': 100}, [
                    (0, 10, {'p1': 3}),
                    (10, 15, {'p2': 1.5}),]),])
        emission_config = configs.config_for(
            make_vessel_info(engine_rpm=100), ev.Mode.TRANSIT)
        assert_that(
            emission_config.low_load_adjustment_factors,
            low_load_adjustment_factors((0, 10, {'p1': 3}),
                                        (10, 15, {'p2': 1.5})))

    def test_returns_empty_adjustment_factors_if_no_match(
            self, make_vessel_info):
        configs = self.make_configs(
            low_load_adjustment_factors=[({'engine_rpm': 400},
                                          [(0, 10, {'p1': 2})])])
        emission_config = configs.config_for(
            make_vessel_info(engine_rpm=100), ev.Mode.TRANSIT)
        assert emission_config.low_load_adjustment_factors == []


class TestVesselInfoGuesser:
    @pytest.fixture
    def make_guesser(self, make_vessel_info_attrs):
        def factory(
                info_guess_data, *, build_times=None,
                add_required_ship_type_sizes=True, add_required_defaults=True):
            build_times = build_times or []
            if add_required_ship_type_sizes:
                for ship_type in cfg.VALID_SHIP_TYPE_SIZE_UNITS:
                    info_guess_data.append(
                        ({'ship_type': ship_type},
                         make_vessel_info_attrs(ship_type=ship_type)))
            if add_required_defaults:
                info_guess_data.append(({}, make_vessel_info_attrs()))
                build_times.append(({}, 1))
            guess_configs = [
                cfg.MatchConfig({'match_criteria': match_criteria}
                                | vessel_data)
                for match_criteria, vessel_data in info_guess_data]
            build_time_configs = [
                cfg.MatchConfig({'match_criteria': match_criteria}
                                | {'build_time_years': build_time_years})
                for match_criteria, build_time_years in build_times]
            return cfg.VesselInfoGuesser(guess_configs, build_time_configs)

        return factory

    def test_returns_vessel_info_if_info_given(
            self, make_guesser, make_vessel_info_attrs):
        guesser = make_guesser([])
        attrs = make_vessel_info_attrs()
        assert_that(
            guesser.guess_missing_vessel_info(**attrs), has_entries(attrs))

    @pytest.mark.parametrize(
        'missing_attrs', [[f.name] for f in dc.fields(cfg.VesselInfo)])
    @pytest.mark.parametrize('attr_none', [True, False])
    def test_guesses_missing_vessel_info(
            self, make_guesser, make_vessel_info_attrs, missing_attrs,
            attr_none):
        existing_attrs = make_vessel_info_attrs()
        if missing_attrs[0] in ['ship_type', 'size', 'size_unit']:
            missing_attrs = ['ship_type', 'size', 'size_unit']
            attrs = make_vessel_info_attrs()
        else:
            attrs = make_vessel_info_attrs(
                ship_type=existing_attrs['ship_type'])
        guesser = make_guesser([
            ({'length': {'ge': 0, 'lt': 100},
              'width': 3.14159}, make_vessel_info_attrs()),
            ({'length': {'ge': 100, 'lt': 200},
              'width': 2.71828}, make_vessel_info_attrs()),
            ({'length': {'ge': 100, 'lt': 200}, 'width': 3.14159}, attrs),
            ({}, make_vessel_info_attrs()),])
        for missing_attr in missing_attrs:
            if attr_none:
                existing_attrs[missing_attr] = None
            else:
                del existing_attrs[missing_attr]
        guess = guesser.guess_missing_vessel_info(
            length=150, width=3.14159, **existing_attrs)
        assert_that(
            guess,
            has_entries({
                k: v
                for k, v in existing_attrs.items()
                if k not in missing_attrs}))
        for missing_attr in missing_attrs:
            assert guess[missing_attr] == attrs[missing_attr]

    @pytest.mark.parametrize('attr_none', [True, False])
    def test_guesses_all_missing_vessel_info(
            self, make_guesser, make_vessel_info_attrs, attr_none):
        attrs = make_vessel_info_attrs()
        guesser = make_guesser([({'length': 150}, attrs)])
        existing_attrs = {}
        if attr_none:
            existing_attrs = {k: None for k in make_vessel_info_attrs()}
        assert_that(
            guesser.guess_missing_vessel_info(length=150, **existing_attrs),
            has_entries(attrs))

    def test_collects_attributes_from_multiple_configs(
            self, make_guesser, make_vessel_info_attrs):
        attr_names = iter(make_vessel_info_attrs())
        attr1 = next(
            a for a in attr_names
            if a not in ['ship_type', 'size', 'size_unit'])
        attr2 = next(
            a for a in attr_names
            if a not in ['ship_type', 'size', 'size_unit'])
        attr_rest = [
            a for a in make_vessel_info_attrs() if a not in [attr1, attr2]]
        attrs1 = make_vessel_info_attrs(only_attrs=[attr1])
        attrs2 = make_vessel_info_attrs(only_attrs=[attr2])
        attrs3 = make_vessel_info_attrs(only_attrs=attr_rest)
        guesser = make_guesser([
            ({'length': 150}, attrs1),
            ({'length': 150, 'width': 31}, make_vessel_info_attrs()),
            ({}, attrs2),
            ({'length': 150, 'width': 30}, attrs3),
            ({'width': 30}, attrs1),])
        assert_that(
            guesser.guess_missing_vessel_info(length=150, width=30),
            has_entries(attrs3 | attrs2 | attrs1))

    def test_matches_on_attributes_from_earlier_configs(
            self, make_guesser, make_vessel_info_attrs):
        attrs1 = make_vessel_info_attrs(
            only_attrs=['engine_rpm'], engine_rpm=123)
        attrs2 = make_vessel_info_attrs()
        guesser = make_guesser([
            ({'length': 150}, attrs1),
            ({'engine_rpm': 123}, attrs2),
            ({}, make_vessel_info_attrs()),])
        assert_that(
            guesser.guess_missing_vessel_info(length=150, width=30),
            has_entries(attrs2 | attrs1))

    def test_doesnt_use_size_and_unit_if_type_from_values_doesnt_match(
            self, make_guesser, make_vessel_info_attrs):
        guesser = make_guesser([
            ({},
             make_vessel_info_attrs(
                 engine_kw=1000, ship_type='container_ship', size=5000,
                 size_unit='teu')),
            ({},
             make_vessel_info_attrs(
                 engine_kw=2000, ship_type='bulk_carrier', size=1000,
                 size_unit='dwt')),])
        assert_that(
            guesser.guess_missing_vessel_info(ship_type='bulk_carrier'),
            has_entries(engine_kw=1000, size=1000, size_unit='dwt'))

    def test_doesnt_use_size_and_unit_if_type_different_even_if_unit_matches(
            self, make_guesser, make_vessel_info_attrs):
        guesser = make_guesser([
            ({},
             make_vessel_info_attrs(
                 engine_kw=1000, ship_type='oil_tanker', size=5000,
                 size_unit='dwt')),
            ({},
             make_vessel_info_attrs(
                 engine_kw=2000, ship_type='bulk_carrier', size=1000,
                 size_unit='dwt')),])
        assert_that(
            guesser.guess_missing_vessel_info(ship_type='bulk_carrier'),
            has_entries(engine_kw=1000, size=1000, size_unit='dwt'))

    def test_uses_size_and_unit_if_type_matches(
            self, make_guesser, make_vessel_info_attrs):
        guesser = make_guesser([
            ({},
             make_vessel_info_attrs(
                 engine_kw=1000, ship_type='bulk_carrier', size=5000,
                 size_unit='dwt')),
            ({},
             make_vessel_info_attrs(
                 engine_kw=2000, ship_type='bulk_carrier', size=1000,
                 size_unit='dwt')),])
        assert_that(
            guesser.guess_missing_vessel_info(ship_type='bulk_carrier'),
            has_entries(engine_kw=1000, size=5000, size_unit='dwt'))

    def test_uses_nox_tier_for_given_keel_laid_year(
            self, make_guesser, make_vessel_info_attrs):
        guesser = make_guesser([
            ({'keel_laid_year': 2000},
             make_vessel_info_attrs(
                 only_attrs=['engine_nox_tier'],
                 engine_nox_tier=cfg.EngineNOxTier.TIER1)),
            ({'keel_laid_year': 2002},
             make_vessel_info_attrs(
                 only_attrs=['engine_nox_tier'],
                 engine_nox_tier=cfg.EngineNOxTier.TIER2)),
            ({'keel_laid_year': {'ge': 2003, 'lt': 9999}},
             make_vessel_info_attrs(
                 only_attrs=['engine_nox_tier'],
                 engine_nox_tier=cfg.EngineNOxTier.TIER3)),])
        assert_that(
            guesser.guess_missing_vessel_info(
                engine_category=cfg.EngineCategory.C3, keel_laid_year=2002,
                year_of_build=2004),
            has_entries(engine_nox_tier=cfg.EngineNOxTier.TIER2))

    def test_uses_nox_tier_for_keel_laid_year_derived_via_given_info(
            self, make_guesser, make_vessel_info_attrs):
        guesser = make_guesser([
            ({'keel_laid_year': 2002},
             make_vessel_info_attrs(
                 only_attrs=['engine_nox_tier'],
                 engine_nox_tier=cfg.EngineNOxTier.TIER2)),
            ({},
             make_vessel_info_attrs(
                 only_attrs=['engine_nox_tier'],
                 engine_nox_tier=cfg.EngineNOxTier.TIER3)),], build_times=[
                     ({'ship_type': 'bulk_carrier'}, 2),
                     ({'ship_type': 'container_ship'}, 3), ({}, 4)])
        assert_that(
            guesser.guess_missing_vessel_info(
                engine_category=cfg.EngineCategory.C3,
                ship_type='container_ship', keel_laid_year=None,
                year_of_build=2005),
            has_entries(engine_nox_tier=cfg.EngineNOxTier.TIER2))

    def test_uses_nox_tier_for_keel_laid_year_derived_via_guessed_info(
            self, make_guesser, make_vessel_info_attrs):
        guesser = make_guesser(
            [
                ({'ais_type': 70, 'length': 100},
                 make_vessel_info_attrs(
                     only_attrs=['ship_type', 'size', 'size_unit'],
                     ship_type='bulk_carrier')),
                ({'ais_type': 70, 'length': 200},
                 make_vessel_info_attrs(
                     only_attrs=['ship_type', 'size', 'size_unit'],
                     ship_type='container_ship')),
                ({'keel_laid_year': 2002},
                 make_vessel_info_attrs(
                     only_attrs=['engine_nox_tier'],
                     engine_nox_tier=cfg.EngineNOxTier.TIER2)),
                ({},
                 make_vessel_info_attrs(
                     only_attrs=['engine_nox_tier'],
                     engine_nox_tier=cfg.EngineNOxTier.TIER3)),],
            build_times=[({'ship_type': 'bulk_carrier'}, 2),
                         ({'ship_type': 'container_ship'}, 3), ({}, 4)],
        )
        assert_that(
            guesser.guess_missing_vessel_info(
                engine_category=cfg.EngineCategory.C3, ais_type=70, length=200,
                keel_laid_year=None, year_of_build=2005),
            has_entries(engine_nox_tier=cfg.EngineNOxTier.TIER2))

    @pytest.mark.parametrize(
        'engine_category', [cfg.EngineCategory.C1, cfg.EngineCategory.C2])
    def test_doesnt_bother_with_nox_tier_for_c1_c2_vessels(
            self, make_guesser, make_vessel_info_attrs, engine_category):
        guesser = make_guesser([
            ({'keel_laid_year': 2002},
             make_vessel_info_attrs(
                 only_attrs=['engine_nox_tier'],
                 engine_nox_tier=cfg.EngineNOxTier.TIER2)),
            ({},
             make_vessel_info_attrs(
                 only_attrs=['engine_nox_tier'],
                 engine_nox_tier=cfg.EngineNOxTier.TIER3)),], build_times=[
                     ({'ship_type': 'container_ship'}, 3)])
        assert_that(
            guesser.guess_missing_vessel_info(
                engine_category=engine_category, ship_type='container_ship',
                keel_laid_year=None, year_of_build=2005),
            has_entries(engine_nox_tier=cfg.EngineNOxTier.TIER3))

    def test_uses_given_nox_tier_if_keel_laid_year_given(
            self, make_guesser, make_vessel_info_attrs):
        guesser = make_guesser([
            ({'keel_laid_year': 2000},
             make_vessel_info_attrs(
                 only_attrs=['engine_nox_tier'],
                 engine_nox_tier=cfg.EngineNOxTier.TIER1)),])
        assert_that(
            guesser.guess_missing_vessel_info(
                engine_category=cfg.EngineCategory.C3, keel_laid_year=2000,
                engine_nox_tier=cfg.EngineNOxTier.TIER3),
            has_entries(engine_nox_tier=cfg.EngineNOxTier.TIER3))

    def test_uses_given_nox_tier_if_keel_laid_year_derived_from_year_of_build(
            self, make_guesser, make_vessel_info_attrs):
        guesser = make_guesser([
            ({'keel_laid_year': 2002},
             make_vessel_info_attrs(
                 only_attrs=['engine_nox_tier'],
                 engine_nox_tier=cfg.EngineNOxTier.TIER1)),],
                               build_times=[({}, 3)])
        assert_that(
            guesser.guess_missing_vessel_info(
                engine_category=cfg.EngineCategory.C3,
                ship_type='container_ship', keel_laid_year=None,
                year_of_build=2005, engine_nox_tier=cfg.EngineNOxTier.TIER3),
            has_entries(engine_nox_tier=cfg.EngineNOxTier.TIER3))

    def test_construction_raises_on_invalid_attr_name(
            self, make_guesser, make_vessel_info_attrs):
        with pytest.raises(ValueError):
            make_guesser([
                ({}, make_vessel_info_attrs(not_a_vessel_info_attr=123))])

    def test_construction_raises_on_invalid_attr_type(
            self, make_guesser, make_vessel_info_attrs):
        with pytest.raises(ValueError):
            make_guesser([
                ({}, make_vessel_info_attrs(engine_rpm='not a number'))])

    def test_construction_raises_if_default_attributes_incomplete(
            self, make_guesser, make_vessel_info_attrs):
        missing_attr = next(
            a for a in make_vessel_info_attrs()
            if a not in ['ship_type', 'size', 'size_unit'])
        attr_names = [a for a in make_vessel_info_attrs() if a != missing_attr]
        with pytest.raises(ValueError):
            make_guesser([({}, make_vessel_info_attrs(only_attrs=attr_names))],
                         build_times=[({}, 1)], add_required_defaults=False)

    def test_construction_accepts_default_attributes_across_multiple_entries(
            self, make_guesser, make_vessel_info_attrs):
        missing_attr = next(
            a for a in make_vessel_info_attrs()
            if a not in ['ship_type', 'size', 'size_unit'])
        attr_names = [a for a in make_vessel_info_attrs() if a != missing_attr]
        make_guesser([
            ({}, make_vessel_info_attrs(only_attrs=attr_names)),
            ({}, make_vessel_info_attrs(only_attrs=[missing_attr])),],
                     build_times=[({}, 1)], add_required_defaults=False)

    def test_construction_raises_if_size_unit_doesnt_match_ship_type(
            self, make_guesser, make_vessel_info_attrs):
        with pytest.raises(ValueError):
            make_guesser([({},
                           make_vessel_info_attrs(
                               ship_type='oil_tanker', size_unit='teu'))])

    @pytest.mark.parametrize(
        'attrs',
        list(
            it.chain(['ship_type', 'size', 'size_unit'],
                     it.combinations(['ship_type', 'size', 'size_unit'], 2))))
    def test_construction_raises_if_ship_type_and_size_not_specified_together(
            self, make_guesser, make_vessel_info_attrs, attrs):
        with pytest.raises(ValueError):
            make_guesser([({}, make_vessel_info_attrs(only_attrs=attrs))])

    @pytest.mark.parametrize(
        'missing_ship_type', list(cfg.VALID_SHIP_TYPE_SIZE_UNITS))
    def test_construction_raises_if_ship_type_size_missing(
            self, make_guesser, make_vessel_info_attrs, missing_ship_type):
        info_guess_data = [({'ship_type': ship_type},
                            make_vessel_info_attrs(ship_type=ship_type))
                           for ship_type in cfg.VALID_SHIP_TYPE_SIZE_UNITS
                           if ship_type != missing_ship_type]
        with pytest.raises(ValueError):
            make_guesser(info_guess_data, add_required_ship_type_sizes=False)

    def test_construction_raises_on_invalid_build_time(self, make_guesser):
        with pytest.raises(ValueError):
            make_guesser([], build_times=[({}, 'not a number')])

    def test_construction_raises_on_missing_default_build_time(
            self, make_guesser, make_vessel_info_attrs):
        with pytest.raises(ValueError):
            make_guesser([({}, make_vessel_info_attrs())], build_times=[],
                         add_required_defaults=False)

    def test_default_vessel_info_is_first_config_without_criteria(
            self, make_guesser, make_vessel_info_attrs):
        attrs = make_vessel_info_attrs()
        guesser = make_guesser([
            ({'length': 30}, make_vessel_info_attrs()),
            ({}, attrs),
            ({'width': 150}, make_vessel_info_attrs()),
            ({}, make_vessel_info_attrs()),], build_times=[({}, 1)],
                               add_required_defaults=False)
        assert_that(guesser.default_vessel_info, has_properties(attrs))
