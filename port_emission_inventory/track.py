import collections
import dataclasses as dc
import functools
import logging
import math
import numbers as nr
import typing as t

import pendulum

import port_emission_inventory.utils as utils

AVG_EARTH_RADIUS = 6370986
MAX_CALCULATED_SPEED = 16


def _attr_repr(self, attr_names):
    attrs = [(n, getattr(self, n)) for n in attr_names]
    members_str = ', '.join(f'{k}: {repr(v)}' for k, v in attrs)
    return '<{}: {{{}}}>'.format(type(self).__name__, members_str)


def _attr_eq(self, other, attr_names):
    for attr_name in attr_names:
        try:
            if getattr(self, attr_name) != getattr(other, attr_name):
                return False
        except AttributeError:
            return False
    return True


def great_circle_distance(lon1, lat1, lon2, lat2):
    """Calculate the great-circle distance in meters."""
    lon1, lat1, lon2, lat2 = map(math.radians, (lon1, lat1, lon2, lat2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    d = (math.sin(dlat * 0.5)**2) + math.cos(lat1) * math.cos(lat2) * (
        math.sin(dlon * 0.5)**2)
    return 2 * AVG_EARTH_RADIUS * math.atan2(math.sqrt(d), math.sqrt(1 - d))


def bearing(lon1, lat1, lon2, lat2):
    """
    Calculate bearing from one position to another relative to north.

    Uses a simple planar projection, which yields reasonably accurate results
    across short distances, but doesn't work across the poles or the
    antimeridian.
    """
    target_lon = lon2 - lon1
    target_lat = lat2 - lat1
    return (math.degrees(math.atan2(target_lon, target_lat)) + 360) % 360


def average_bearing(b1, b2):
    if abs(b1 - b2) > 180:
        if b1 < b2:
            b1 += 360
        else:
            b2 += 360
    return ((b1 + b2) / 2) % 360


def surrounding_context_iter(iterable, past_context_size, future_context_size):
    """
    Iterate with past and future elements.

    Iterates over tuples (past, current, future), where past and future are
    deques containing immediately preceding or following elements in the
    iterable.

    The deques are reused, so data must be copied if it is needed beyond the
    iteration.
    """
    assert past_context_size >= 1
    past = collections.deque(maxlen=past_context_size)
    future = collections.deque(maxlen=future_context_size + 1)
    for element in iterable:
        if len(future) == future.maxlen:
            current = future.popleft()
            yield past, current, future
            past.append(current)
        future.append(element)
    while future:
        current = future.popleft()
        yield past, current, future
        past.append(current)


@dc.dataclass
class Dynamics:
    _attributes = ('ts', 'sog', 'stw')

    def __init__(self, ts, sog, cog, tide_flow, tide_bearing):
        self.ts = ts
        self.sog = sog
        self.update_stw_from(cog, tide_flow, tide_bearing)

    def __repr__(self):
        return _attr_repr(self, self._attributes)

    def __eq__(self, other):
        return _attr_eq(self, other, self._attributes)

    def update_stw_from(self, cog, tide_flow, tide_bearing):
        self.stw = self._speed_through_water(
            self.sog, cog, tide_flow, tide_bearing)

    @staticmethod
    def _speed_through_water(sog, cog, tide_flow, tide_bearing):
        """
        Calculate the speed through water considering tide current.

        The speeds must be the same unit, which will also be the unit of the
        output. cog and tide_bearing must be in degrees.
        """
        if not tide_flow:
            return sog
        diff_rad = math.radians(cog - tide_bearing)
        return math.sqrt(
            sog**2 + tide_flow**2 - (2 * sog * tide_flow * math.cos(diff_rad)))


class Position:
    _attributes = (
        '_dynamics', 'lon', 'lat', 'cog', 'heading', 'tide_flow',
        'tide_bearing')

    def __init__(
            self, ts, lon, lat, sog, cog, heading, tide_flow=0,
            tide_bearing=0):
        self._dynamics = Dynamics(ts, sog, cog, tide_flow, tide_bearing)
        self.lon = lon
        self.lat = lat
        self.cog = cog
        self.heading = heading
        self._tide_flow = tide_flow
        self._tide_bearing = tide_bearing

    def __repr__(self):
        return _attr_repr(self, self._attributes)

    def __eq__(self, other):
        return _attr_eq(self, other, self._attributes)

    @property
    def ts(self):
        return self._dynamics.ts

    @property
    def sog(self):
        return self._dynamics.sog

    @property
    def stw(self):
        return self._dynamics.stw

    def _get_recalc_property(self, *, attr):
        return getattr(self, f'_{attr}')

    def _set_recalc_property(self, value, *, attr):
        setattr(self, f'_{attr}', value)
        self.recalculate_dynamics()

    for attr in ['tide_flow', 'tide_bearing']:
        locals()[attr] = property(
            functools.partial(_get_recalc_property, attr=attr),
            functools.partial(_set_recalc_property, attr=attr))

    def recalculate_dynamics(self):
        self._dynamics.update_stw_from(
            self.cog, self.tide_flow, self.tide_bearing)


class Segment:
    def __init__(self, start, end):
        if start.ts > end.ts:
            raise ValueError('Start must not be after end.')
        self.start = start
        self.end = end
        self._distance = None

    def __repr__(self):
        return _attr_repr(self, ('start', 'end', 'distance', 'duration'))

    @property
    def distance(self):
        if self._distance is None:
            self._distance = great_circle_distance(
                self.start.lon, self.start.lat, self.end.lon, self.end.lat)
        return self._distance

    def duration(self):
        return self.end.ts.diff(self.start.ts)


class Track:
    def __init__(self, *, position_class=Position, segment_class=Segment):
        self.position_class = position_class
        self.segment_class = segment_class
        self.positions = []
        self.segments = []

    @classmethod
    def sanitized_from_positions(
        cls, position_dicts, stw_is_plausible: t.Callable[[float], bool],
        distance_covered_is_plausible: t.Callable[
            [nr.Number, float, float, nr.Number, float, float], bool]):
        sanitizations = {
            'num_discarded': 0, 'num_sogs': 0, 'num_cogs': 0,
            'num_headings': 0, 'sogs': set()}
        track = cls()
        for past, current, future in surrounding_context_iter(position_dicts,
                                                              3, 1):
            if cls._position_is_outlier(current, past,
                                        distance_covered_is_plausible):
                sanitizations['num_discarded'] += 1
                continue
            sog = current['sog']
            cog = current['cog']
            heading = current['heading']
            try:
                tide_flow = current['tide_flow']
                tide_bearing = current['tide_bearing']
                assert tide_flow >= 0 and 0 <= tide_bearing < 360
            except (KeyError, AssertionError, TypeError):
                tide_flow, tide_bearing = 0, 0
            if sog is None or not stw_is_plausible(sog):
                sanitizations['num_sogs'] += 1
                sanitizations['sogs'].add(sog)
                sog = cls._calculate_sog(current, past, future)
            if cog is None:
                sanitizations['num_cogs'] += 0
                cog = cls._calculate_cog(current, past, future)
            if heading is None:
                sanitizations['num_headings'] += 1
                heading = cog
            track.append_position(
                pendulum.from_timestamp(current['ts']), current['lon'],
                current['lat'], sog, cog, heading, tide_flow, tide_bearing)
        if any(sanitizations.values()):
            logging.getLogger(cls.__name__).debug(
                'Sanitization during track creation: '
                f'{sanitizations["num_discarded"]} outliers, '
                f'{sanitizations["num_sogs"]} sogs ({sanitizations["sogs"]}), '
                f'{sanitizations["num_cogs"]} cogs, '
                f'{sanitizations["num_headings"]} headings.')
        return track

    @classmethod
    def _position_is_outlier(
            cls, current, past, distance_covered_is_plausible):
        if not past:
            return False
        ts = sum(p['ts'] for p in past) / len(past)
        lon = sum(p['lon'] for p in past) / len(past)
        lat = sum(p['lat'] for p in past) / len(past)
        return not distance_covered_is_plausible(
            ts, lon, lat, current['ts'], current['lon'], current['lat'])

    @classmethod
    def _calculate_sog(cls, current, past, future):
        pos_pairs = []
        if past:
            pos_pairs.append((past[-1], current))
        if future:
            pos_pairs.append((current, future[0]))
        if not pos_pairs:
            return 0
        acc = 0
        for left, right in pos_pairs:
            distance = great_circle_distance(
                left['lon'], left['lat'], right['lon'], right['lat'])
            hours = (right['ts'] - left['ts']) / 3600
            try:
                acc += utils.m_to_nm(distance / hours)
            except ZeroDivisionError:
                pass
        return min(acc / len(pos_pairs), MAX_CALCULATED_SPEED)

    @classmethod
    def _calculate_cog(cls, current, past, future):
        pos_pairs = []
        if past:
            pos_pairs.append((past[-1], current))
        if future:
            pos_pairs.append((current, future[0]))
        if not pos_pairs:
            return 0
        cogs = []
        for left, right in pos_pairs:
            cogs.append(
                bearing(left['lon'], left['lat'], right['lon'], right['lat']))
        if len(cogs) == 1:
            return cogs[0]
        return average_bearing(*cogs)

    @property
    def distance(self):
        return sum(s.distance for s in self.segments)

    @property
    def duration(self):
        return sum((s.duration() for s in self.segments),
                   start=pendulum.duration())

    def partial_track(self, start_ts, end_ts):
        """Create a shallow copy bounded to the given interval."""
        if start_ts > end_ts:
            raise ValueError('Start must not be after end.')
        try:
            start_idx = next(
                i for i, p in enumerate(self.positions) if p.ts >= start_ts)
        except StopIteration:
            return type(self)()
        if (start_ts == self.positions[0].ts
                and end_ts == self.positions[-1].ts):
            return self
        positions = [p for p in self.positions[start_idx:] if p.ts <= end_ts]
        segments = self.segments[start_idx:start_idx + len(positions) - 1]
        partial_track = type(self)()
        partial_track.positions = positions
        partial_track.segments = segments
        return partial_track

    def append_position(
            self, ts, lon, lat, sog, cog, heading, tide_flow=0,
            tide_bearing=0):
        """
        Append a position.

        Also adds the segment connecting the last position to the new one.
        """
        pos = self.position_class(
            ts, lon, lat, sog, cog, heading, tide_flow, tide_bearing)
        self.positions.append(pos)
        try:
            segment = self.segment_class(self.positions[-2], pos)
            self.segments.append(segment)
        except IndexError:
            pass
