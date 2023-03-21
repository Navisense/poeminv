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

import abc
import dataclasses as dc
import enum
import itertools as it
import logging
import numbers as nr

import poeminv.event as ev
import poeminv.util as util

VALID_SHIP_TYPE_SIZE_UNITS = {
    'barge': ['n/a'],
    'crew_supply': ['n/a'],
    'excursion': ['n/a'],
    'fishing': ['n/a'],
    'towboat_pushboat': ['n/a'],
    'dredging': ['n/a'],
    'sailing': ['n/a'],
    'recreational': ['n/a'],
    'pilot': ['n/a'],
    'tug': ['n/a'],
    'workboat': ['n/a'],
    'government': ['n/a'],
    'bulk_carrier': ['dwt'],
    'chemical_tanker': ['dwt'],
    'container_ship': ['teu'],
    'cruise': ['gt'],
    'ferry_passenger': ['gt', 'n/a'],
    'ferry_roro_passenger': ['gt'],
    'general_cargo': ['dwt'],
    'liquified_gas_tanker': ['dwt'],
    'offshort_support_drillship': ['n/a'],
    'oil_tanker': ['dwt'],
    'other_service': ['n/a'],
    'other_tanker': ['n/a'],
    'reefer': ['n/a'],
    'roro': ['gt'],
    'vehicle_carrier': ['number_vehicles'],
    'misc': ['n/a'],}

ShipSizeUnit = util.ValueContainsStrEnum(
    'ShipSizeUnit', [
        unit.upper()
        for unit in set(it.chain(*VALID_SHIP_TYPE_SIZE_UNITS.values()))])


class EngineGroup(util.ValueContainsStrEnum):
    PROPULSION: str = enum.auto()
    AUXILIARY: str = enum.auto()
    BOILER: str = enum.auto()


class EngineCategory(util.ValueContainsStrEnum):
    C1: str = enum.auto()
    C2: str = enum.auto()
    C3: str = enum.auto()


class EngineNOxTier(util.ValueContainsIntEnum):
    UNCLASSIFIED: int = 0
    TIER1: int = 1
    TIER2: int = 2
    TIER3: int = 3


@dc.dataclass
class VesselInfo:
    max_speed: nr.Number
    engine_kw: nr.Number
    engine_rpm: nr.Number
    engine_category: str
    engine_nox_tier: int
    ship_type: str
    size: nr.Number
    size_unit: str

    def __post_init__(self):
        try:
            assert self.max_speed > 0
            assert self.engine_kw > 0
            assert self.engine_rpm > 0
            assert self.engine_category in EngineCategory
            assert self.engine_nox_tier in EngineNOxTier
            assert self.size >= 0
            assert self.size_unit in VALID_SHIP_TYPE_SIZE_UNITS[self.ship_type]
        except (AssertionError, TypeError) as e:
            raise ValueError(f'Invalid info {self}.') from e


class Range:
    def __init__(self, ge, lt):
        self._ge = ge
        self._lt = lt

    def __contains__(self, value):
        return self._ge <= value < self._lt


class Criterion(abc.ABC):
    VALID_NAMES = (
        {f.name
         for f in dc.fields(VesselInfo)}
        | {
            'engine_group', 'length', 'width', 'ais_type', 'does_tug_jobs',
            'does_pilot_transfer', 'keel_laid_year'})

    def __init__(self, name):
        self.name = name
        self._assert_valid()

    def _assert_valid(self):
        if self.name not in self.VALID_NAMES:
            raise ValueError(f'Invalid criterion name {self.name}.')
        if self.name == 'ship_type' and not self._value_is_one_of(
                VALID_SHIP_TYPE_SIZE_UNITS):
            raise ValueError(f'Invalid ship type for {self.name}.')
        if self.name == 'size_unit' and not self._value_is_one_of(
                ShipSizeUnit):
            raise ValueError(f'Invalid size unit for {self.name}.')
        if self.name == 'engine_category' and not self._value_is_one_of(
                EngineCategory):
            raise ValueError(f'Invalid engine category for {self.name}.')
        if self.name == 'engine_nox_tier' and not self._value_is_one_of(
                EngineNOxTier):
            raise ValueError(f'Invalid engine NOx tier for {self.name}.')
        if self.name == 'engine_group' and not self._value_is_one_of(
                EngineGroup):
            raise ValueError(f'Invalid engine group for {self.name}.')

    @abc.abstractmethod
    def _value_is_one_of(self, values):
        raise NotImplementedError

    @abc.abstractmethod
    def matches(self, **values):
        raise NotImplementedError


class EqualsCriterion(Criterion):
    def __init__(self, name, value):
        self._value = value
        super().__init__(name)

    def _value_is_one_of(self, values):
        return self._value in values

    def matches(self, **values):
        try:
            return values[self.name] == self._value
        except KeyError:
            return False


class RangeCriterion(Criterion):
    def __init__(self, name, ge, lt):
        self._range = Range(ge, lt)
        super().__init__(name)

    def _value_is_one_of(self, values):
        return False

    def matches(self, **values):
        try:
            return values[self.name] in self._range
        except (KeyError, TypeError):
            return False


class DisjunctionCriterion(Criterion):
    def __init__(self, name, *criteria):
        if any(c.name != name for c in criteria):
            raise ValueError('Attribute names in criteria don\'t match.')
        self._criteria = criteria
        super().__init__(name)

    def _value_is_one_of(self, values):
        return all(c._value_is_one_of(values) for c in self._criteria)

    def matches(self, **values):
        return any(c.matches(**values) for c in self._criteria)


class MatchConfig:
    """
    A config that can be matched to specific use cases.

    Basically a dictionary of data, along with some criteria that can be
    checked against values to see if the data is relevant to them.
    """
    def __init__(self, match_config):
        try:
            self.criteria = {
                name: self._criterion_from_dict(name, criterion)
                for name, criterion in match_config['match_criteria'].items()}
        except KeyError:
            raise ValueError(f'Missing criteria in {match_config}.')
        self.data = {
            k: v
            for k, v in match_config.items()
            if k != 'match_criteria'}

    def _criterion_from_dict(self, name, spec):
        if not isinstance(spec, dict):
            return EqualsCriterion(name, spec)
        try:
            return RangeCriterion(name, spec['ge'], spec['lt'])
        except KeyError:
            pass
        try:
            sub_criteria = [
                self._criterion_from_dict(name, d) for d in spec['any_of']]
            return DisjunctionCriterion(name, *sub_criteria)
        except KeyError:
            raise ValueError(f'Invalid criterion for {name}: {spec}.')

    def matches(self, **values):
        return all(c.matches(**values) for c in self.criteria.values())


class Config:
    def __init__(self, config):
        try:
            base_values = {
                name: self._match_configs_from(match_configs)
                for name, match_configs in config['base_values'].items()}
            pollutants = {
                name: self._match_configs_from(match_configs)
                for name, match_configs in config['pollutants'].items()}
            engine_powers = self._match_configs_from(
                config['default_engine_powers'])
            vessel_info_guess_data = self._match_configs_from(
                config['vessel_info_guess_data'])
            average_vessel_build_times = self._match_configs_from(
                config['average_vessel_build_times'])
            low_load_adjustment_factors = self._match_configs_from(
                config['low_load_adjustment_factors'])
        except KeyError as e:
            raise ValueError('Missing config part.') from e
        self._emission_configs = EmissionConfigs(
            base_values, pollutants, engine_powers,
            low_load_adjustment_factors)
        self._vessel_info_guesser = VesselInfoGuesser(
            vessel_info_guess_data, average_vessel_build_times)

    @staticmethod
    def _match_configs_from(match_configs_list):
        return [
            MatchConfig(match_config) for match_config in match_configs_list]

    @staticmethod
    def from_yaml_path(yaml_path):
        import yaml
        with open(yaml_path, 'rb') as f:
            return Config(yaml.load(f, yaml.Loader))

    @property
    def default_vessel_info(self):
        return self._vessel_info_guesser.default_vessel_info

    def emission_config_for(self, vessel_info, mode):
        return self._emission_configs.config_for(vessel_info, mode)

    def guess_missing_vessel_info(self, **values):
        return self._vessel_info_guesser.guess_missing_vessel_info(**values)


class EmissionConfigs:
    def __init__(
            self, base_values, pollutants, engine_powers,
            low_load_adjustment_factors):
        self._base_values = base_values
        self._pollutants = pollutants
        self._engine_powers = engine_powers
        self._low_load_adjustment_factors = low_load_adjustment_factors
        self._assert_valid_config()
        self.logger = logging.getLogger(type(self).__name__)

    def _assert_valid_config(self):
        for c in it.chain(*self._base_values.values()):
            if not isinstance(c.data.get('g_per_kwh'), nr.Number):
                raise ValueError(
                    f'Emissions (g_per_kwh) must be a number in {c.data}.')
        for c in it.chain(*self._pollutants.values()):
            if c.data.get('base_value_name') not in self._base_values:
                raise ValueError(f'No existing base_value_name in {c.data}.')
            if not isinstance(c.data.get('multiplier', 1), nr.Number):
                raise ValueError(f'Multiplier must be a number in {c.data}.')
            if not isinstance(c.data.get('offset_g_per_kwh', 0), nr.Number):
                raise ValueError(f'Offset must be a number in {c.data}.')
        missing_default_engine_powers = {'auxiliary', 'boiler'}
        for c in self._engine_powers:
            if any(not isinstance(c.data.get(mode), nr.Number)
                   for mode in ev.Mode):
                raise ValueError(
                    f'Default engine powers must be a number in {c.data}.')
            if set(c.criteria) == {'engine_group'}:
                for p in list(missing_default_engine_powers):
                    if c.criteria['engine_group'].matches(engine_group=p):
                        missing_default_engine_powers.discard(p)
        if missing_default_engine_powers:
            raise ValueError(
                'No criteria-less engine powers for engine groups '
                f'{missing_default_engine_powers}.')
        for c in self._low_load_adjustment_factors:
            if not c.data.get('range_factors'):
                raise ValueError(
                    f'No low-load adjustment defined in {c.data}.')
            for rf in c.data['range_factors']:
                range_ = rf.get('range', {})
                factors = rf.get('factors', {})
                if 'ge' not in range_ or 'lt' not in range_:
                    raise ValueError(f'No range defined in {rf}.')
                if not all(isinstance(v, nr.Number) for v in factors.values()):
                    raise ValueError(
                        f'Adjustment factors must be a number in {factors}.')

    def config_for(self, vessel_info, mode):
        emission_factors = {
            e: self._emission_factors_for(vessel_info, e)
            for e in EmissionConfig.EMISSIONS_ENGINE_GROUPS}
        engine_powers = {
            e: self._engine_powers_for(vessel_info, e, mode)
            for e in EmissionConfig.ENGINE_POWER_ENGINE_GROUPS}
        low_load_adjustment_factors = self._low_load_adjustment_factors_for(
            vessel_info)
        return EmissionConfig(
            emission_factors, engine_powers, low_load_adjustment_factors)

    def _emission_factors_for(self, vessel_info, engine_group):
        emission_factors = {}
        for pollutant, configs in self._pollutants.items():
            try:
                pollutant_config = next(
                    self._matching_configs(
                        configs, engine_group=engine_group,
                        **dc.asdict(vessel_info)))
            except StopIteration:
                continue
            base_value_name = pollutant_config['base_value_name']
            try:
                base_value_config = next(
                    self._matching_configs(
                        self._base_values[base_value_name],
                        engine_group=engine_group, **dc.asdict(vessel_info)))
            except StopIteration:
                self.logger.warning(
                    f'Unable to calculate {pollutant} emissions for '
                    f'{engine_group} and {vessel_info} because no '
                    'matching base value exists.')
                continue
            emission_factors[pollutant] = (
                pollutant_config.get('offset_g_per_kwh', 0)
                + base_value_config['g_per_kwh']
                * pollutant_config.get('multiplier', 1))
        return emission_factors

    def _matching_configs(self, match_configs, **values):
        for match_config in match_configs:
            if match_config.matches(**values):
                yield match_config.data

    def _engine_powers_for(self, vessel_info, engine_group, mode):
        for match_config in self._engine_powers:
            if match_config.matches(engine_group=engine_group,
                                    **dc.asdict(vessel_info)):
                break
        else:
            self.logger.warning(
                f'No {engine_group} engine powers matching {vessel_info}, '
                'using the last one.')
        return match_config.data[mode]

    def _low_load_adjustment_factors_for(self, vessel_info):
        for match_config in self._low_load_adjustment_factors:
            if match_config.matches(**dc.asdict(vessel_info)):
                return self._make_range_factors(
                    match_config.data['range_factors'])
        return []

    def _make_range_factors(self, range_factors):
        return [(Range(c['range']['ge'], c['range']['lt']), c['factors'])
                for c in range_factors]


class EmissionConfig:
    EMISSIONS_ENGINE_GROUPS = frozenset(['propulsion', 'auxiliary', 'boiler'])
    ENGINE_POWER_ENGINE_GROUPS = frozenset(['auxiliary', 'boiler'])

    def __init__(
            self, emission_factors, engine_powers,
            low_load_adjustment_factors):
        if set(emission_factors) != self.EMISSIONS_ENGINE_GROUPS:
            raise ValueError(
                'Missing or invalid emission factor engine groups.')
        if set(engine_powers) != self.ENGINE_POWER_ENGINE_GROUPS:
            raise ValueError('Missing or invalid engine power engine groups.')
        self._emission_factors = emission_factors
        self._engine_powers = engine_powers
        self.low_load_adjustment_factors = low_load_adjustment_factors

    def engine_power(self, engine_group):
        if engine_group not in self.ENGINE_POWER_ENGINE_GROUPS:
            raise ValueError('Invalid engine group.')
        return self._engine_powers[engine_group]

    def emissions_from_energy(self, engine_group, kwh):
        try:
            emission_factors = self._emission_factors[engine_group]
        except KeyError:
            raise ValueError('Invalid engine group.')
        return {
            pollutant: kwh * g_per_kwh
            for pollutant, g_per_kwh in emission_factors.items()}


class VesselInfoGuesser:
    _FIELD_NAMES = frozenset([field.name for field in dc.fields(VesselInfo)])

    def __init__(self, guess_data, average_vessel_build_times):
        self._guess_data = guess_data
        self._average_vessel_build_times = average_vessel_build_times
        self._assert_valid_config()
        self.default_vessel_info = VesselInfo(
            **self.guess_missing_vessel_info())

    def _assert_valid_config(self):
        vessel_info_fields = {f.name: f for f in dc.fields(VesselInfo)}
        type_and_size = ['ship_type', 'size', 'size_unit']
        default_vessel_info_fields_seen = set()
        ship_type_sizes_seen = {st: False for st in VALID_SHIP_TYPE_SIZE_UNITS}
        vessel_info_default_kwargs = {
            'max_speed': 1, 'engine_kw': 1, 'engine_rpm': 1,
            'engine_category': 'c1', 'engine_nox_tier': 1, 'ship_type': 'misc',
            'size': 0, 'size_unit': 'n/a'}
        for c in self._guess_data:
            try:
                VesselInfo(**(vessel_info_default_kwargs | c.data))
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f'Unable to instantiate VesselInfo from {c.data}.') from e
            if any(a in c.data for a in type_and_size):
                if not all(a in c.data for a in type_and_size):
                    raise ValueError(
                        f'Attributes {type_and_size} must always be specified '
                        f'together. Not the case with {c.data}.')
                ship_type = c.data['ship_type']
                size_unit = c.data['size_unit']
                valid_units = VALID_SHIP_TYPE_SIZE_UNITS.get(ship_type, [])
                if size_unit not in valid_units:
                    raise ValueError(
                        f'{size_unit} is not a valid unit for {ship_type}.')
            if not c.criteria:
                default_vessel_info_fields_seen |= set(c.data)
            if set(c.criteria) == {'ship_type'}:
                for ship_type in VALID_SHIP_TYPE_SIZE_UNITS:
                    if (all(criterion.matches(ship_type=ship_type)
                            for criterion in c.criteria.values())
                            and 'size' in c.data):
                        ship_type_sizes_seen[ship_type] = True
        missing_defaults = (
            set(vessel_info_fields) - default_vessel_info_fields_seen)
        if missing_defaults:
            raise ValueError(
                f'Attributes {missing_defaults} are not present in a '
                'criteria-less config.')
        missing_ship_type_sizes = {
            st
            for st, has_size in ship_type_sizes_seen.items()
            if not has_size}
        if missing_ship_type_sizes:
            raise ValueError(
                'No sizes and units specified for ship types '
                f'{missing_ship_type_sizes}.')
        default_build_time_seen = False
        for c in self._average_vessel_build_times:
            if not c.criteria:
                default_build_time_seen = True
            if not isinstance(c.data.get('build_time_years'), nr.Number):
                raise ValueError(
                    f'build_time_years is not a number in {c.data}.')
        if not default_build_time_seen:
            raise ValueError(
                'No criteria-less average vessel build time exists.')

    def guess_missing_vessel_info(self, **values):
        """
        Create arguments representing complete vessel information.

        Returns a kwarg dictionary to construct a VesselInfo object based on
        given values.

        If any values needed to construct a VesselInfo object in the input are
        missing or None, looks up suitable default values in the vessel data
        defined in the configuration. Additional values can be specified in the
        input (e.g. length, width, ais_type) that are used to match the
        criteria of the data. For each attribute, the first set of data
        including that attribute whose criteria match is chosen.

        Some special handling applies to guessing engine_nox_tier since it
        relies on keel_laid_year, which in turn may only be known through
        year_of_build. If engine_category is c3 (the only one for which NOx
        tier is interesting), keel_laid_year was not initially known, but
        year_of_build is, a second round of guessing is done. First, the
        keel_laid_year is calculated from year_of_build and the average vessel
        build time, which is looked up using all known vessel information
        (including e.g. ship_type which may have been guessed based on
        ais_type). This is used to make another, more informed guess of
        engine_nox_tier.

        An additional restriction applies to ship_type, size, and size_unit: if
        ship_type is specified as part of values, size and size_unit contained
        in a data set are are only used if the ship_type in that data set is
        the same as the one in values. That's to prevent a size_unit being
        assigned to a ship_type where it doesn't make sense.

        For similar reasons, whenever size or size_unit are part of values,
        ship_type must also be specified, or a ValueError is raised.

        Only missing values are replaced with guesses, existing data is left as
        it was.
        """
        if (values.get('ship_type') is None and
            (values.get('size') or values.get('size_unit') is not None)):
            raise ValueError(
                f'Size specified without a ship type in {values}.')
        attrs = {
            k: v
            for k, v in values.items()
            if k in self._FIELD_NAMES and v is not None}
        attrs = self._guess_missing_attrs(attrs, **values)
        attrs = self._maybe_improve_nox_tier_guess(attrs, values)
        return attrs

    def _guess_missing_attrs(self, attrs, **values):
        for match_config in self._guess_data:
            if match_config.matches(**(values | attrs)):
                attrs = self._attrs_with_extra_data(attrs, match_config.data)
            if len(attrs) == len(self._FIELD_NAMES):
                break
        return attrs

    def _attrs_with_extra_data(self, attrs, data):
        usable_new_attrs = {
            k: v
            for k, v in data.items()
            if k not in ['size', 'size_unit']}
        attrs = usable_new_attrs | attrs
        existing_ship_type = attrs.get('ship_type')
        new_ship_type = data.get('ship_type')
        if (new_ship_type is not None
                and (existing_ship_type in [None, new_ship_type])):
            attrs.setdefault('size', data['size'])
            attrs.setdefault('size_unit', data['size_unit'])
        return attrs

    def _maybe_improve_nox_tier_guess(self, attrs, values):
        if (attrs['engine_category'] == 'c3'
                and values.pop('keel_laid_year', None) is None
                and values.get('year_of_build') is not None):
            # We couldn't guess a proper engine_nox_tier without
            # keel_laid_year, but now we can derive it from year_of_build.
            del attrs['engine_nox_tier']
            build_time = self._find_average_build_time(**(values | attrs))
            keel_laid_year = values['year_of_build'] - build_time
            attrs = self._guess_missing_attrs(
                attrs, **values, keel_laid_year=keel_laid_year)
        return attrs

    def _find_average_build_time(self, **values):
        matching_config = next(
            c for c in self._average_vessel_build_times if c.matches(**values))
        return matching_config.data['build_time_years']
