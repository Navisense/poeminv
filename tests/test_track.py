import math
import unittest.mock as umock

from hamcrest import *
import pendulum
import pytest

import port_emission_inventory.track as trk


def pdts(t):
    return pendulum.from_timestamp(t)


def d(seconds=0):
    return pendulum.duration(seconds=seconds)


def test_great_circle_distance():
    # Reference distance from luftlinie.org.
    hh = 9.992196, 53.553406
    nyc = -74.005974, 40.714268
    hh_nyc = trk.great_circle_distance(*hh, *nyc)
    assert hh_nyc == pytest.approx(6129310, abs=1000)

    lombardsbruecke = 9.9978, 53.5568
    kennedybruecke = 9.9984, 53.5576
    bridge_dist = trk.great_circle_distance(*lombardsbruecke, *kennedybruecke)
    assert bridge_dist == pytest.approx(97, abs=1)


def test_bearing():
    assert trk.bearing(0, 0, 0, 0) == 0
    assert trk.bearing(0, 0, 0, 1) == 0
    assert trk.bearing(0, 0, 0, 10) == 0
    assert trk.bearing(0, 0, 1, 1) == 45
    assert trk.bearing(0, 0, 10, 10) == 45
    assert trk.bearing(0, 0, 1, 0) == 90
    assert trk.bearing(0, 0, 10, 0) == 90
    assert trk.bearing(0, 0, 1, -1) == 135
    assert trk.bearing(0, 0, 10, -10) == 135
    assert trk.bearing(0, 0, 0, -1) == 180
    assert trk.bearing(0, 0, 0, -10) == 180
    assert trk.bearing(0, 0, -1, -1) == 225
    assert trk.bearing(0, 0, -10, -10) == 225
    assert trk.bearing(0, 0, -1, 0) == 270
    assert trk.bearing(0, 0, -10, 0) == 270
    assert trk.bearing(0, 0, -1, 1) == 315
    assert trk.bearing(0, 0, -10, 10) == 315

    assert trk.bearing(5, 7, 5, 7) == 0
    assert trk.bearing(5, 7, 5, 8) == 0
    assert trk.bearing(5, 7, 5, 17) == 0
    assert trk.bearing(5, 7, 6, 8) == 45
    assert trk.bearing(5, 7, 15, 17) == 45
    assert trk.bearing(5, 7, 6, 7) == 90
    assert trk.bearing(5, 7, 15, 7) == 90
    assert trk.bearing(5, 7, 6, 6) == 135
    assert trk.bearing(5, 7, 15, -3) == 135
    assert trk.bearing(5, 7, 5, 6) == 180
    assert trk.bearing(5, 7, 5, -3) == 180
    assert trk.bearing(5, 7, 4, 6) == 225
    assert trk.bearing(5, 7, -5, -3) == 225
    assert trk.bearing(5, 7, 4, 7) == 270
    assert trk.bearing(5, 7, -5, 7) == 270
    assert trk.bearing(5, 7, 4, 8) == 315
    assert trk.bearing(5, 7, -5, 17) == 315


def test_average_bearing():
    assert trk.average_bearing(10, 20) == 15
    assert trk.average_bearing(350, 10) == 0
    assert trk.average_bearing(340, 10) == 355
    assert trk.average_bearing(350, 20) == 5
    assert trk.average_bearing(10, 200) == 285
    assert trk.average_bearing(200, 200) == 200
    assert trk.average_bearing(200, 240) == 220


class TestSurroundingContextIter:
    def test_empty(self):
        assert list(trk.surrounding_context_iter([], 2, 2)) == []

    def test_single(self):
        enumerated_contexts = enumerate(
            trk.surrounding_context_iter([5], 10, 10))
        for i, (past, current, future) in enumerated_contexts:
            assert i == 0
            assert len(past) == len(future) == 0
            assert current == 5

    def test_plenty(self):
        enumerated_contexts = enumerate(
            trk.surrounding_context_iter(
                range(10), past_context_size=2, future_context_size=3))
        for i, (past, current, future) in enumerated_contexts:
            assert i == current
            assert list(past) == [j for j in range(i - 2, i) if j >= 0]
            assert list(future) == [j for j in range(i + 1, i + 4) if j < 10]

    def test_supports_only_past(self):
        for _, _, future in trk.surrounding_context_iter(
                range(10), past_context_size=2, future_context_size=0):
            assert len(future) == 0


class TestDynamics:
    def test_calculates_stw_on_construction(self):
        stw_data = [((1, 0, 1, 180), 2), ((2, 0, 3, 180), 5),
                    ((1, 0, 1, 0), 0), ((5, 0, 2, 0), 3),
                    ((1, 0, 1, 90), pytest.approx(math.sqrt(2))),
                    ((2, 0, 3, 90), pytest.approx(math.sqrt(13))),
                    ((1, 0, 1, 270), pytest.approx(math.sqrt(2))),
                    ((2, 0, 3, 270), pytest.approx(math.sqrt(13)))]
        for dynamics_args, stw in stw_data:
            assert trk.Dynamics(0, *dynamics_args).stw == stw

    def test_updates_stw(self):
        d = trk.Dynamics(0, 4, 0, 2, 180)
        assert d.stw == 6
        d.update_stw_from(45, 3, 135)
        assert d.stw == 5


class TestPosition:
    def test_calculates_stw_on_construction(self):
        pos = trk.Position(10, 11, 12, 6, 0, 14, 2, 180)
        assert_that(
            pos,
            has_properties(
                ts=10, lon=11, lat=12, sog=6, cog=0, heading=14, tide_flow=2,
                tide_bearing=180, stw=8))

    def test_recalculates_stw_on_changed_tide_flow(self):
        pos = trk.Position(10, 0, 0, 6, 0, 0, 2, 180)
        assert pos.stw == 8
        pos.tide_flow = 3
        assert pos.stw == 9

    def test_recalculates_stw_on_changed_tide_bearing(self):
        pos = trk.Position(10, 0, 0, 4, 0, 0, 3, 180)
        assert pos.stw == 7
        pos.tide_bearing = 270
        assert pos.stw == 5


class TestSegment:
    def test_duration(self):
        position1 = trk.Position(
            pendulum.from_timestamp(10), 11, 12, 13, 14, 15, 16, 17)
        position2 = trk.Position(
            pendulum.from_timestamp(20), 21, 22, 23, 24, 25, 26, 27)
        segment = trk.Segment(position1, position2)
        assert segment.duration() == d(10)


class TestTrack:
    @pytest.fixture
    def patch_abs_lon_diff_distance(self, monkeypatch):
        def abs_lon_diff_distance(lon1, lat1, lon2, lat2):
            return abs(lon1 - lon2)

        monkeypatch.setattr(
            trk, 'great_circle_distance', abs_lon_diff_distance)

    @pytest.fixture
    def patch_abs_lat_diff_bearing(self, monkeypatch):
        def abs_lat_diff_bearing(lon1, lat1, lon2, lat2):
            return abs(lat1 - lat2)

        monkeypatch.setattr(trk, 'bearing', abs_lat_diff_bearing)

    @pytest.fixture
    def stw_is_plausible(self):
        return umock.Mock()

    @pytest.fixture
    def distance_covered_is_plausible(self):
        return umock.Mock()

    @staticmethod
    def make_pos_dict(ts, lon, lat, sog, cog, heading):
        return {
            'ts': ts, 'lon': lon, 'lat': lat, 'sog': sog, 'cog': cog,
            'heading': heading}

    def test_partial_track_on_empty(self):
        track = trk.Track()
        actual = track.partial_track(pdts(0), pdts(1000))
        assert actual.positions == []
        assert actual.segments == []

    def test_partial_track_on_same_bounds_returns_self(self):
        track = trk.Track()
        track.append_position(pdts(0), 1, 2, 3, 4, 5, 6, 7)
        track.append_position(pdts(10), 11, 12, 13, 14, 15, 16, 17)
        track.append_position(pdts(20), 21, 22, 23, 24, 25, 26, 27)
        assert track.partial_track(pdts(0), pdts(20)) is track

    def test_partial_track_on_subset(self):
        track = trk.Track()
        track.append_position(pdts(0), 1, 2, 3, 4, 5, 6, 7)
        track.append_position(pdts(10), 11, 12, 13, 14, 15, 16, 17)
        track.append_position(pdts(20), 21, 22, 23, 24, 25, 26, 27)
        track.append_position(pdts(30), 31, 32, 33, 34, 35, 36, 37)
        track.append_position(pdts(40), 41, 42, 43, 44, 45, 46, 47)
        actual = track.partial_track(pdts(10), pdts(35))
        assert actual.positions == track.positions[1:4]
        assert actual.segments == track.segments[1:3]

    def test_partial_track_on_mismatched_timeframe(self):
        track = trk.Track()
        track.append_position(pdts(0), 1, 2, 3, 4, 5, 6, 7)
        track.append_position(pdts(10), 11, 12, 13, 14, 15, 16, 17)
        track.append_position(pdts(20), 21, 22, 23, 24, 25, 26, 27)
        actual = track.partial_track(pdts(100), pdts(200))
        assert actual.positions == []
        assert actual.segments == []

    def test_partial_track_on_empty_subset(self):
        track = trk.Track()
        track.append_position(pdts(0), 1, 2, 3, 4, 5, 6, 7)
        track.append_position(pdts(10), 11, 12, 13, 14, 15, 16, 17)
        track.append_position(pdts(20), 21, 22, 23, 24, 25, 26, 27)
        actual = track.partial_track(pdts(11), pdts(19))
        assert actual.positions == []
        assert actual.segments == []

    def test_partial_track_on_single_position(self):
        track = trk.Track()
        track.append_position(pdts(0), 1, 2, 3, 4, 5, 6, 7)
        track.append_position(pdts(10), 11, 12, 13, 14, 15, 16, 17)
        track.append_position(pdts(20), 21, 22, 23, 24, 25, 26, 27)
        actual = track.partial_track(pdts(8), pdts(12))
        assert actual.positions == track.positions[1:2]
        assert actual.segments == []

    def test_partial_track_on_beyond_start(self):
        track = trk.Track()
        track.append_position(pdts(100), 1, 2, 3, 4, 5, 6, 7)
        track.append_position(pdts(110), 11, 12, 13, 14, 15, 16, 17)
        track.append_position(pdts(120), 21, 22, 23, 24, 25, 26, 27)
        track.append_position(pdts(130), 31, 32, 33, 34, 35, 36, 37)
        track.append_position(pdts(140), 41, 42, 43, 44, 45, 46, 47)
        actual = track.partial_track(pdts(10), pdts(130))
        assert actual.positions == track.positions[:4]
        assert actual.segments == track.segments[:3]

    def test_partial_track_on_beyond_end(self):
        track = trk.Track()
        track.append_position(pdts(0), 1, 2, 3, 4, 5, 6, 7)
        track.append_position(pdts(10), 11, 12, 13, 14, 15, 16, 17)
        track.append_position(pdts(20), 21, 22, 23, 24, 25, 26, 27)
        track.append_position(pdts(30), 31, 32, 33, 34, 35, 36, 37)
        track.append_position(pdts(40), 41, 42, 43, 44, 45, 46, 47)
        actual = track.partial_track(pdts(10), pdts(100))
        assert actual.positions == track.positions[1:]
        assert actual.segments == track.segments[1:]

    def test_sanitized_parses_empty(
            self, stw_is_plausible, distance_covered_is_plausible):
        track = trk.Track.sanitized_from_positions(
            [], stw_is_plausible, distance_covered_is_plausible)
        assert track.positions == []

    def test_sanitized_parses_single_position(
            self, stw_is_plausible, distance_covered_is_plausible):
        positions = [self.make_pos_dict(1, 2, 3, 5, 7, 11)]
        track = trk.Track.sanitized_from_positions(
            positions, stw_is_plausible, distance_covered_is_plausible)
        assert_that(
            track.positions,
            contains_exactly(
                has_properties(
                    ts=pdts(1), lon=2, lat=3, sog=5, cog=7, heading=11)))

    def test_sanitized_parses_track(
            self, stw_is_plausible, distance_covered_is_plausible):
        positions = [
            self.make_pos_dict(1, 2, 3, 5, 7, 11),
            self.make_pos_dict(1000001, 12, 13, 15, 17, 111),
            self.make_pos_dict(2000001, 22, 23, 25, 27, 211)]
        track = trk.Track.sanitized_from_positions(
            positions, stw_is_plausible, distance_covered_is_plausible)
        assert_that(
            track.positions,
            contains_exactly(
                has_properties(
                    ts=pdts(1), lon=2, lat=3, sog=5, cog=7, heading=11),
                has_properties(
                    ts=pdts(1000001), lon=12, lat=13, sog=15, cog=17,
                    heading=111),
                has_properties(
                    ts=pdts(2000001), lon=22, lat=23, sog=25, cog=27,
                    heading=211)))

    def test_sanitized_falls_back_to_calculated_sog_on_invalid(
            self, stw_is_plausible, distance_covered_is_plausible,
            patch_abs_lon_diff_distance):
        stw_is_plausible.return_value = False
        positions = [
            self.make_pos_dict(0, 0, 0, None, 0, 0),
            self.make_pos_dict(3600, 10 * 1852, 0, 7.7, 0, 0),
            self.make_pos_dict(7200, 22 * 1852, 0, None, 0, 0)]
        track = trk.Track.sanitized_from_positions(
            positions, stw_is_plausible, distance_covered_is_plausible)
        stw_is_plausible.assert_called_once_with(7.7)
        assert_that(
            track.positions,
            contains_exactly(
                has_properties(sog=10), has_properties(sog=11),
                has_properties(sog=12)))

    def test_sanitized_limits_calculated_sog(
            self, stw_is_plausible, distance_covered_is_plausible,
            patch_abs_lon_diff_distance):
        stw_is_plausible.return_value = False
        positions = [
            self.make_pos_dict(0, 0, 0, None, 0, 0),
            self.make_pos_dict(
                3600, (trk.MAX_CALCULATED_SPEED + 1) * 1852, 0, None, 0, 0)]
        track = trk.Track.sanitized_from_positions(
            positions, stw_is_plausible, distance_covered_is_plausible)
        assert_that(
            track.positions,
            contains_exactly(
                has_properties(sog=trk.MAX_CALCULATED_SPEED),
                has_properties(sog=trk.MAX_CALCULATED_SPEED)))

    def test_sanitized_falls_back_to_calculated_cog_on_invalid(
            self, stw_is_plausible, distance_covered_is_plausible,
            patch_abs_lat_diff_bearing):
        positions = [
            self.make_pos_dict(0, 0, 0, 0, None, 0),
            self.make_pos_dict(3600, 0, 10, 0, None, 0),
            self.make_pos_dict(7200, 0, 22, 0, None, 0)]
        track = trk.Track.sanitized_from_positions(
            positions, stw_is_plausible, distance_covered_is_plausible)
        assert_that(
            track.positions,
            contains_exactly(
                has_properties(cog=10), has_properties(cog=11),
                has_properties(cog=12)))

    def test_sanitized_fallback_to_calculated_cog_handles_north_crossing(
            self, stw_is_plausible, distance_covered_is_plausible,
            patch_abs_lat_diff_bearing):
        positions = [
            self.make_pos_dict(0, 0, 0, 0, None, 0),
            self.make_pos_dict(3600, 0, 340, 0, None, 0),
            self.make_pos_dict(7200, 0, 350, 0, None, 0)]
        track = trk.Track.sanitized_from_positions(
            positions, stw_is_plausible, distance_covered_is_plausible)
        assert_that(
            track.positions,
            contains_exactly(
                has_properties(cog=340), has_properties(cog=355),
                has_properties(cog=10)))

    def test_sanitized_falls_back_to_cog_on_invalid_heading(
            self, stw_is_plausible, distance_covered_is_plausible):
        positions = [
            self.make_pos_dict(0, 0, 0, 0, 1, None),
            self.make_pos_dict(3600, 0, 0, 0, 2, None),
            self.make_pos_dict(7200, 0, 0, 0, 3, None)]
        track = trk.Track.sanitized_from_positions(
            positions, stw_is_plausible, distance_covered_is_plausible)
        assert_that(
            track.positions,
            contains_exactly(
                has_properties(heading=1), has_properties(heading=2),
                has_properties(heading=3)))

    def test_sanitized_falls_back_to_calculated_cog_on_both_invalid(
            self, stw_is_plausible, distance_covered_is_plausible,
            patch_abs_lat_diff_bearing):
        positions = [
            self.make_pos_dict(0, 0, 0, 0, None, None),
            self.make_pos_dict(3600, 0, 10, 0, None, None),
            self.make_pos_dict(7200, 0, 22, 0, None, None)]
        track = trk.Track.sanitized_from_positions(
            positions, stw_is_plausible, distance_covered_is_plausible)
        assert_that(
            track.positions,
            contains_exactly(
                has_properties(cog=10, heading=10),
                has_properties(cog=11, heading=11),
                has_properties(cog=12, heading=12)))

    def test_sanitized_falls_back_to_zero_on_single_position(
            self, stw_is_plausible, distance_covered_is_plausible):
        positions = [self.make_pos_dict(0, 0, 0, None, None, None)]
        track = trk.Track.sanitized_from_positions(
            positions, stw_is_plausible, distance_covered_is_plausible)
        assert_that(
            track.positions,
            contains_exactly(has_properties(sog=0, cog=0, heading=0)))

    def test_sanitized_discards_outliers_based_on_past(
            self, stw_is_plausible, distance_covered_is_plausible):
        distance_covered_is_plausible.side_effect = [True, False, False, True]
        positions = [
            self.make_pos_dict(0, 10, 100, 0, None, None),
            self.make_pos_dict(10, 20, 120, 1, None, None),
            self.make_pos_dict(30, 25, 125, 2, None, None),
            self.make_pos_dict(60, 35, 145, 3, None, None),
            self.make_pos_dict(110, 70, 150, 4, None, None)]
        track = trk.Track.sanitized_from_positions(
            positions, stw_is_plausible, distance_covered_is_plausible)
        distance_calls = (distance_covered_is_plausible.call_args_list)
        assert distance_calls == [
            umock.call(0, 10, 100, 10, 20, 120),
            umock.call(5, 15, 110, 30, 25, 125),
            umock.call(40 / 3, 55 / 3, 115, 60, 35, 145),
            umock.call(100 / 3, 80 / 3, 130, 110, 70, 150)]
        assert_that(
            track.positions,
            contains_exactly(
                has_properties(sog=0), has_properties(sog=1),
                has_properties(sog=4)))

    def test_duration_on_empty(self):
        assert trk.Track().duration == pendulum.duration(seconds=0)

    def test_duration_on_single_position(self):
        track = trk.Track()
        track.append_position(pdts(10), 11, 12, 13, 14, 15, 16, 17)
        assert track.duration == pendulum.duration(seconds=0)

    def test_duration_on_single_segment(self):
        track = trk.Track()
        track.append_position(pdts(10), 11, 12, 13, 14, 15, 16, 17)
        track.append_position(pdts(20), 21, 22, 23, 24, 25, 26, 27)
        assert track.duration == pendulum.duration(seconds=10)

    def test_duration_on_multiple_segments(self):
        track = trk.Track()
        track.append_position(pdts(10), 1, 2, 3, 4, 5, 6, 7)
        track.append_position(pdts(25), 11, 12, 13, 14, 15, 16, 17)
        track.append_position(pdts(120), 21, 22, 23, 24, 25, 26, 27)
        assert track.duration == pendulum.duration(seconds=110)
