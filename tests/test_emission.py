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

import unittest.mock as umock

from hamcrest import *
import pendulum
import pytest

import poeminv.config as cfg
import poeminv.emission as em
import poeminv.event as event


def make_ts_speeds_distance_track(*values):
    track = event.Track()
    distance_meters = None
    values_iter = iter(values)
    for ts_seconds, sog, stw in values_iter:
        tide_flow = abs(sog - stw)
        tide_bearing = 0 if sog >= stw else 180
        track.append_position(
            pendulum.from_timestamp(ts_seconds), 0, 0, sog, 0, 0, tide_flow,
            tide_bearing)
        if distance_meters is not None:
            track.segments[-1]._distance = distance_meters * 1852
        try:
            distance_meters = next(values_iter)
        except StopIteration:
            break
    return track


@pytest.fixture
def mocked_segment_sanitizer():
    def adjusted_segment_hours(segment):
        return segment.duration.total_hours()

    sanitizer = umock.Mock()
    sanitizer.adjusted_segment_hours.side_effect = adjusted_segment_hours
    return sanitizer


class TestSegmentDurationSanitizer:
    @pytest.fixture
    def sanitizer(self):
        return em.SegmentDurationSanitizer(
            max_fuel_calc_distance_deviation=0.2,
            max_fuel_calc_duration_increase_factor=9)

    def test_reduces_duration_if_speeds_are_high(self, sanitizer):
        track = make_ts_speeds_distance_track((0, 6, 0), 8, (7200, 7, 0))
        dist_by_speed = 6 + 7
        max_dist = 8 * 1.2
        assert max_dist < dist_by_speed
        adjustment_factor = max_dist / dist_by_speed
        adjusted_hours = sanitizer.adjusted_segment_hours(track.segments[0])
        assert adjusted_hours == 2 * adjustment_factor

    def test_increases_duration_if_speeds_are_low(self, sanitizer):
        track = make_ts_speeds_distance_track((0, 1, 0), 8, (7200, 2, 0))
        dist_by_speed = 1 + 2
        min_dist = 8 * 0.8
        assert min_dist > dist_by_speed
        adjustment_factor = min_dist / dist_by_speed
        adjusted_hours = sanitizer.adjusted_segment_hours(track.segments[0])
        assert adjusted_hours == 2 * adjustment_factor

    def test_doesnt_do_anything_on_0_sog(self, sanitizer):
        track = make_ts_speeds_distance_track((0, 0, 0), 8, (7200, 0, 0))
        assert sanitizer.adjusted_segment_hours(track.segments[0]) == 2

    def test_caps_increase_factor(self, sanitizer):
        track = make_ts_speeds_distance_track((0, 0.1, 0), 8, (7200, 0.2, 0))
        assert sanitizer.adjusted_segment_hours(track.segments[0]) == 18


class TestEmissionCalculator:
    @pytest.fixture
    def make_calculator(self, mocked_segment_sanitizer):
        class MockEmissionConfig:
            def __init__(self):
                self._engine_powers = {}
                self._emissions = {}
                self.low_load_adjustment_factors = []

            def engine_power(self, engine_group):
                return self._engine_powers[engine_group]

            def emissions_from_energy(self, engine_group, kwh):
                try:
                    return self._emissions[(engine_group, kwh)]
                except KeyError:
                    return {}

        def factory():
            calculator = em.EmissionCalculator(
                umock.Mock(sea_margin_adjustment_factor=1),
                cfg.VesselInfo(
                    max_speed=10, engine_kw=1000, engine_rpm=100,
                    engine_category='c3', engine_nox_tier=1,
                    ship_type='container_ship', size=3000, size_unit='teu'),
                segment_duration_sanitizer=mocked_segment_sanitizer)
            calculator.config.emission_config_for.return_value = (
                MockEmissionConfig())
            return calculator

        return factory

    @pytest.fixture
    def calculator(self, make_calculator):
        return make_calculator()

    @pytest.fixture
    def emission_config(self, calculator):
        return calculator.config.emission_config_for.return_value

    def test_propulsion_load_at_stw_is_cubed_fraction_of_max_speed(
            self, calculator):
        assert calculator.propulsion_load_at_stw(0) == 0
        assert calculator.propulsion_load_at_stw(1) == pytest.approx(0.001)
        assert calculator.propulsion_load_at_stw(5) == 0.125
        assert calculator.propulsion_load_at_stw(10) == 1

    def test_propulsion_load_at_stw_is_capped_at_1(self, calculator):
        assert calculator.propulsion_load_at_stw(10) == 1
        assert calculator.propulsion_load_at_stw(11) == 1
        assert calculator.propulsion_load_at_stw(float('inf')) == 1

    def test_propulsion_load_at_stw_adjusts_with_sea_margin(self, calculator):
        calculator.config.sea_margin_adjustment_factor = 1.25
        assert calculator.propulsion_load_at_stw(1) == pytest.approx(0.00125)
        assert calculator.propulsion_load_at_stw(5) == 0.15625
        assert calculator.propulsion_load_at_stw(9.5) == 1
        assert calculator.propulsion_load_at_stw(10) == 1

    def test_segment_propulsion_emissions_on_same_stw(
            self, calculator, emission_config):
        track = make_ts_speeds_distance_track((0, 0, 5), 5, (7200, 0, 5))
        expected_kwh = 1000 * 2 * 0.5**3
        emission_config._emissions[('propulsion', expected_kwh)] = {'p1': 1}
        actual = calculator.segment_propulsion_emissions(
            track.segments[0], emission_config)
        assert actual == {'p1': 1}

    def test_segment_propulsion_emissions_averages_loads_from_different_stw(
            self, calculator, emission_config):
        track = make_ts_speeds_distance_track((0, 0, 2.5), 5, (7200, 0, 7.5))
        expected_load = (0.25**3 + 0.75**3) / 2
        expected_kwh = 1000 * 2 * expected_load
        emission_config._emissions[('propulsion', expected_kwh)] = {'p1': 1}
        actual = calculator.segment_propulsion_emissions(
            track.segments[0], emission_config)
        assert actual == {'p1': 1}

    def test_segment_propulsion_emissions_uses_sanitized_segment_durations(
            self, calculator, mocked_segment_sanitizer, emission_config):
        def adjusted_segment_hours(segment):
            return 2.5

        adj_hours = mocked_segment_sanitizer.adjusted_segment_hours
        adj_hours.side_effect = (adjusted_segment_hours)
        track = make_ts_speeds_distance_track((0, 0, 7), 6, (7200, 0, 5))
        expected_load = (0.7**3 + 0.5**3) / 2
        expected_kwh = 1000 * 2.5 * expected_load
        emission_config._emissions[('propulsion', expected_kwh)] = {'p1': 1}
        actual = calculator.segment_propulsion_emissions(
            track.segments[0], emission_config)
        assert actual == {'p1': 1}
        adj_hours.assert_called_once_with(track.segments[0])

    def test_segment_propulsion_emissions_adjusts_emissions_for_low_load(
            self, calculator, emission_config):
        track = make_ts_speeds_distance_track((0, 0, 7), 6, (7200, 0, 5))
        expected_load = (0.7**3 + 0.5**3) / 2
        expected_kwh = 1000 * 2 * expected_load
        emission_config._emissions[('propulsion', expected_kwh)] = {
            'p1': 1, 'p2': 2, 'p3': 4}
        emission_config.low_load_adjustment_factors = [
            (cfg.Range(0, expected_load - 0.05), {'p1': 8}),
            (
                cfg.Range(expected_load - 0.05, expected_load + 0.05),
                {'p1': 16.5, 'p3': 32.5, 'p4': 10}),
            (cfg.Range(expected_load + 0.05, 1), {'p2': 3})]
        actual = calculator.segment_propulsion_emissions(
            track.segments[0], emission_config)
        assert actual == {'p1': 16.5, 'p2': 2, 'p3': 130}

    def test_track_emissions_calculates_emissions_on_empty_track(
            self, calculator, emission_config):
        track = make_ts_speeds_distance_track()
        emission_config._engine_powers = {'auxiliary': 200, 'boiler': 400}
        assert calculator.calculate_track_emissions(track,
                                                    event.Mode.TRANSIT) == {}
        calculator.config.emission_config_for.assert_called_once_with(
            calculator.vessel_info, event.Mode.TRANSIT)

    def test_track_emissions_calculates_emissions_on_single_position_track(
            self, calculator, emission_config):
        track = make_ts_speeds_distance_track((0, 0, 10))
        emission_config._engine_powers = {'auxiliary': 200, 'boiler': 400}
        assert calculator.calculate_track_emissions(track,
                                                    event.Mode.TRANSIT) == {}

    def test_track_emissions_calculates_emissions(
            self, calculator, emission_config):
        track = make_ts_speeds_distance_track((0, 0, 10), 10, (5400, 0, 10), 8,
                                              (9000, 0, 5))
        prop_kwh1 = 1500
        prop_kwh2 = 1000 * ((1 + 0.125) / 2)
        emission_config._engine_powers = {'auxiliary': 200, 'boiler': 400}
        emission_config._emissions[('propulsion', prop_kwh1)] = {'p1': 1}
        emission_config._emissions[('propulsion', prop_kwh2)] = {'p4': 32}
        emission_config._emissions[('auxiliary', 500)] = {'p1': 2, 'p2': 4}
        emission_config._emissions[('boiler', 1000)] = {'p1': 8, 'p3': 16}
        actual = calculator.calculate_track_emissions(
            track, event.Mode.MANEUVERING)
        assert actual == {'p1': 11, 'p2': 4, 'p3': 16, 'p4': 32}
        calculator.config.emission_config_for.assert_called_once_with(
            calculator.vessel_info, event.Mode.MANEUVERING)

    def test_track_emissions_raises_on_invalid_mode(self, calculator):
        track = make_ts_speeds_distance_track((0, 0, 10), 10, (5400, 0, 10), 8,
                                              (9000, 0, 5))
        with pytest.raises(ValueError):
            calculator.calculate_track_emissions(track, 'not a valid mode')

    def test_mooring_emissions_calculates_emissions(
            self, calculator, emission_config):
        emission_config._engine_powers = {'auxiliary': 200, 'boiler': 400}
        emission_config._emissions[('auxiliary', 300)] = {'p1': 1, 'p2': 2}
        emission_config._emissions[('boiler', 600)] = {'p2': 4, 'p3': 8}
        actual = calculator.calculate_mooring_emissions(
            pendulum.duration(hours=1.5), event.Mode.HOTELLING)
        assert actual == {'p1': 1, 'p2': 6, 'p3': 8}
        calculator.config.emission_config_for.assert_called_once_with(
            calculator.vessel_info, event.Mode.HOTELLING)

    def test_mooring_emissions_raises_on_invalid_mode(self, calculator):
        with pytest.raises(ValueError):
            calculator.calculate_mooring_emissions(
                pendulum.duration(hours=1.5), 'not a valid mode')
