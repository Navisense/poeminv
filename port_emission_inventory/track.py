import collections
import logging
import math
import numbers as nr
import typing as t

import pendulum

import port_emission_inventory.utils as utils

AVG_EARTH_RADIUS = 6370986


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


def always_true(*args, **kwargs):
    return True


class Longitude(float):
    """A number in the range [-180, 180)."""
    def __new__(cls, value):
        if not -180 <= value < 180:
            raise ValueError('Longitudes must be in range [-180, 180).')
        return super(cls, cls).__new__(cls, value)


class Latitude(float):
    """A number in the range [-90, 90]."""
    def __new__(cls, value):
        if not -90 <= value <= 90:
            raise ValueError('Latitudes must be in range [-90, 90].')
        return super(cls, cls).__new__(cls, value)


class Speed(float):
    """A non-negative number."""
    def __new__(cls, value):
        if value < 0:
            raise ValueError('Speeds must be non-negative.')
        return super(cls, cls).__new__(cls, value)


class Bearing(float):
    """A number in the range [0, 360)."""
    def __new__(cls, value):
        if not 0 <= value < 360:
            raise ValueError('Bearings must be in range [0, 360).')
        return super(cls, cls).__new__(cls, value)


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


class Position:
    """
    Position with data.

    In addition to the attributes ts, lon, lat, sog, cog, heading, tide_flow,
    and tide_bearing, there is a stw (speed through water) property that is
    calculated from sog and tide data.

    All speeds must be in kts, bearings in degrees. tide_bearing is the true
    heading into which the tide is flowing, e.g. if it is 0, the water is
    flowing from south to north.

    The tide_flow and tide_bearing attributes can be changed after
    construction, which causes the stw property to be recalculated to reflect
    the changes.
    """
    _attributes = (
        'ts', 'lon', 'lat', 'cog', 'heading', 'tide_flow', 'tide_bearing')

    def __init__(
            self, ts, lon, lat, sog, cog, heading, tide_flow=0,
            tide_bearing=0):
        self.ts = ts
        self.lon = Longitude(lon)
        self.lat = Latitude(lat)
        self._sog = Speed(sog)
        self.cog = Bearing(cog)
        self.heading = Bearing(heading)
        self.tide_flow = Speed(tide_flow)
        self.tide_bearing = Bearing(tide_bearing)
        self._stw = None

    def __repr__(self):
        return _attr_repr(self, self._attributes)

    def __eq__(self, other):
        return _attr_eq(self, other, self._attributes)

    @property
    def sog(self):
        return self._sog

    @property
    def tide_flow(self):
        return self._tide_flow

    @tide_flow.setter
    def tide_flow(self, value):
        self._tide_flow = Speed(value)
        self._stw = None

    @property
    def tide_bearing(self):
        return self._tide_bearing

    @tide_bearing.setter
    def tide_bearing(self, value):
        self._tide_bearing = Bearing(value)
        self._stw = None

    @property
    def stw(self):
        if self._stw is None:
            self._stw = self._speed_through_water(
                self.sog, self.cog, self.tide_flow, self.tide_bearing)
        return self._stw

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


class Segment:
    """
    A segment between 2 positions.

    Represents the connection between 2 individual positions. Has a distance
    and a duration, which are calculated from coordinates and timestamps of the
    positions. The distance can be passed on constructionn if it is already
    known.
    """
    def __init__(self, start, end, distance=None):
        if start.ts > end.ts:
            raise ValueError('Start must not be after end.')
        self.start = start
        self.end = end
        self._distance = distance

    def __repr__(self):
        return _attr_repr(self, ('start', 'end'))

    @property
    def distance(self):
        if self._distance is None:
            self._distance = great_circle_distance(
                self.start.lon, self.start.lat, self.end.lon, self.end.lat)
        return self._distance

    @property
    def duration(self):
        return self.end.ts.diff(self.start.ts)


class Track:
    """
    A track of positions and segments between them.

    Contains a list of positions, and for each successive pair a segment
    between them representing their connection.

    Each position represents one AIS position update and contains
    - ts: epoch timestamp in seconds
    - lon, lat: coordinates in degrees
    - sog: speed over ground in knots
    - cog, heading: course over ground and true heading in degrees
    - tide_flow, tide_bearing: tide flow and true heading in kts and degrees
    - stw: speed through water in kts, calculated from sog and tide data,
      defaults to sog

    Each position's tide_flow and tide_bearing can also be set later and the
    stw property will be recalculated to reflect those changes.

    Each segments has a distance and a duration that are derived from their
    start and end positions.

    The position_class and segment_class arguments specify which class to use
    for positions and segments. This allows you to use your own subclasses with
    this implementation.

    Tracks can be created empty and filled via append_position(), but it may be
    best to use the sanitized_from_positions() classmethod, which takes a list
    of dictionaries with position data and sanity-checks them against one
    another.
    """
    MAX_CALCULATED_SPEED = 16

    def __init__(self, *, position_class=Position, segment_class=Segment):
        self.position_class = position_class
        self.segment_class = segment_class
        self.positions = []
        self.segments = []

    @classmethod
    def sanitized_from_positions(
        cls,
        position_dicts,
        sog_is_plausible: t.Callable[[float], bool] = always_true,
        distance_covered_is_plausible: t.Callable[
            [nr.Number, float, float, nr.Number, float, float],
            bool] = always_true,
    ):
        """
        Create a track from a list of dictionaries.

        Expects a list of dictionaries, each containing the keys
        - ts: epoch timestamp in seconds, not None
        - lon, lat: not None
        - sog, cog, heading: may be None, but must be valid (i.e. >=0, and <360
            for cog/heading)
        - tide_flow, tide_bearing: optional, but must be valid to be used (>=0,
          and <360 for tide_bearing), default to 0

        If any of sog, cog, or heading are None, or sog is implausible
        according sog_is_plausible, values calculated from the sequence of
        positions are used. The value used for a position is the average of
        that in its adjacent segments. However, the calculated speed is capped
        at MAX_CALCULATED_SPEED. If either of tide_flow and tide_bearing is
        missing, None or invalid, both are set to 0.

        Additionally, positions are discarded entirely if, according to
        distance_covered_is_plausible, the vessel could not have plausibly
        gotten from the average of the past few positions to the current
        position in the claimed time.

        sog_is_plausible must be a function that takes a speed over ground and
        returns whether it is plausible that the ship went that fast.

        distance_covered_is_plausible must be a function that takes 2 sets of
        timestamp and coordinates (i.e. (ts1, lon1, lat1, ts2, lon2, lat2)) and
        returns whether it's plausible the vessel covered that distance in that
        time.
        """
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
            if sog is None or not sog_is_plausible(sog):
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
        return min(acc / len(pos_pairs), cls.MAX_CALCULATED_SPEED)

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
        return sum((s.duration for s in self.segments),
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
