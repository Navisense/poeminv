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

import logging
import numbers as nr

import pendulum

import poeminv.config as cfg
import poeminv.event as ev
import poeminv.util as util


class SegmentDurationSanitizer:
    def __init__(
            self, max_fuel_calc_distance_deviation: nr.Number = 0.25,
            max_fuel_calc_duration_increase_factor: nr.Number = 10) -> None:
        self.max_fuel_calc_distance_deviation = (
            max_fuel_calc_distance_deviation)
        self.max_fuel_calc_duration_increase_factor = (
            max_fuel_calc_duration_increase_factor)

    def adjusted_segment_hours(self, segment: ev.Segment) -> nr.Number:
        """
        Return adjusted segment duration in hours.

        Sanity-checks the reported speed over ground along the segment against
        its distance, and returns an adjusted duration of the segment in hours.
        If speed and distance roughly match, this is just the duration of the
        segment, i.e. the difference in timestamps.

        But if the reported distance (based on sog and duration) differs from
        the actual distance by more than a factor of
        max_fuel_calc_distance_deviation, the duration that is returned is
        changed so the reported distance is within these limits. E.g., if the
        segment is 6nm, 1h, at 3kts, the reported distance (3nm) doesn't match,
        and this method will return a larger duration (the smallest duration d
        such that (1-max_fuel_calc_distance_deviation) * 6nm <= d * 3kts).

        There are 2 exceptions to this: if the sog is 0, no adjustment is made.
        And if the duration has to be increased, it is never increased by more
        than max_fuel_calc_duration_increase_factor.

        The sog of the segment is the average of the sogs at start and end
        position.

        Note that the duration of segments is adjusted, not the speeds, so that
        we don't get wildly unreasonable results from very high speeds when
        calculating fuel consumption.
        """
        segment_hours = segment.duration.total_hours()
        average_sog = (segment.start.sog + segment.end.sog) / 2
        assumed_distance = segment_hours * average_sog
        actual_distance = util.m_to_nm(segment.distance)
        min_distance = (
            actual_distance * (1 - self.max_fuel_calc_distance_deviation))
        max_distance = (
            actual_distance * (1 + self.max_fuel_calc_distance_deviation))
        adjustment_factor = 1
        if assumed_distance != 0:
            if assumed_distance < min_distance:
                adjustment_factor = min_distance / assumed_distance
            elif assumed_distance > max_distance:
                adjustment_factor = max_distance / assumed_distance
        adjustment_factor = min(
            adjustment_factor, self.max_fuel_calc_duration_increase_factor)
        return segment_hours * adjustment_factor


class EmissionCalculator:
    """
    A calculator for vessel emissions.

    A calculator instance is specific to a vessel, information about which is
    passed on construction. It needs a config in which it can look up emission
    factors and data related to the vessel.
    """
    def __init__(
        self, config: cfg.Config, vessel_info: cfg.VesselInfo,
        segment_duration_sanitizer:
        SegmentDurationSanitizer = SegmentDurationSanitizer()
    ) -> None:
        self.config = config
        self.vessel_info = vessel_info
        self.segment_duration_sanitizer = segment_duration_sanitizer
        self.logger = logging.getLogger(f'{__name__}.{type(self).__name__}')

    def calculate_track_emissions(
            self, track: ev.Track,
            mode: ev.Mode) -> util.OpDict[str, nr.Number]:
        """
        Calculate emissions caused on a track.

        Calculates the propulsion emissions by calculating the propulsion load
        on each segment according to the propeller law (relative to the
        vessel's maximum speed), then the energy expended along all segments
        using the vessel's main engine power, then the emissions using
        emissions factors.

        Calculates auxiliary engine and boiler emissions by looking up default
        engine power for the given mode, calculating the energy expended over
        the time of the track, then emissions using emission factors.

        mode must be one of Mode.TRANSIT or Mode.MANEUVERING, or a ValueError
        is raised.

        Returns a dictionary mapping names of pollutants to their amount in
        grams.
        """
        if mode not in (ev.Mode.TRANSIT, ev.Mode.MANEUVERING):
            raise ValueError(f'Invalid mode {mode} for track emissions.')
        emission_config = self.config.emission_config_for(
            self.vessel_info, mode)
        total_emissions = self._propulsion_emissions(track, emission_config)
        for engine_group in ('auxiliary', 'boiler'):
            total_emissions += self._non_propulsion_emissions(
                track.duration, emission_config, engine_group)
        return total_emissions

    def _propulsion_emissions(self, track, emission_config):
        emissions = sum((
            self.segment_propulsion_emissions(s, emission_config)
            for s in track.segments), start=util.OpDict())
        if not emissions:
            self.logger.warning(
                f'No propulsion emissions calculated for {self.vessel_info} '
                f'along {track}.')
        return emissions

    def segment_propulsion_emissions(
            self, segment: ev.Segment, emission_config: cfg.EmissionConfig
    ) -> util.OpDict[str, nr.Number]:
        segment_hours = (
            self.segment_duration_sanitizer.adjusted_segment_hours(segment))
        load = self._segment_load(segment)
        kwh = self.vessel_info.engine_kw * segment_hours * load
        base_emissions = util.OpDict(
            emission_config.emissions_from_energy('propulsion', kwh))
        return self._adjusted_emissions(base_emissions, load, emission_config)

    def _segment_load(self, segment):
        start_load = self.propulsion_load_at_stw(segment.start.stw)
        end_load = self.propulsion_load_at_stw(segment.end.stw)
        return (start_load + end_load) / 2

    def propulsion_load_at_stw(self, stw: ev.Speed) -> nr.Number:
        fraction_of_max_speed = stw / self.vessel_info.max_speed
        load = fraction_of_max_speed**3
        load *= self.config.sea_margin_adjustment_factor
        return min(load, 1)

    def _adjusted_emissions(self, base_emissions, load, emission_config):
        for load_range, adjustment_factors in (
                emission_config.low_load_adjustment_factors):
            if load in load_range:
                return base_emissions * adjustment_factors
        return base_emissions

    def _non_propulsion_emissions(
            self, duration, emission_config, engine_group):
        kw = emission_config.engine_power(engine_group)
        kwh = kw * duration.total_hours()
        emissions = emission_config.emissions_from_energy(engine_group, kwh)
        if not emissions:
            self.logger.warning(
                f'No {engine_group} emissions calculated for '
                f'{self.vessel_info}.')
        return util.OpDict(emissions)

    def calculate_mooring_emissions(
            self, duration: pendulum.Duration,
            mode: ev.Mode) -> util.OpDict[str, nr.Number]:
        """
        Calculate emissions caused during a mooring.

        Calculates auxiliary engine and boiler emissions by looking up default
        engine power for the given mode, calculating the energy expended over
        the duration of the mooring, then emissions using emission factors.

        mode must be one of Mode.HOTELLING or Mode.ANCHORAGE, or a ValueError
        is raised.

        Returns a dictionary mapping names of pollutants to their amount in
        grams.
        """
        if mode not in (ev.Mode.HOTELLING, ev.Mode.ANCHORAGE):
            raise ValueError(f'Invalid mode {mode} for mooring emissions.')
        emission_config = self.config.emission_config_for(
            self.vessel_info, mode)
        return sum((
            self._non_propulsion_emissions(
                duration, emission_config, engine_group)
            for engine_group in ('auxiliary', 'boiler')), start=util.OpDict())
