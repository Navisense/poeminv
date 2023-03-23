# Port emission inventory tools

`poeminv` is a Python library containing a set of tools for automated creation
of port emission inventories.

## Copyright and license

Copyright 2023 Navisense GmbH (https://navisense.de)

The program in this repository is free software: you can redistribute it and/or
modify it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or (at your
option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along
with this program, in the file LICENSE at the top level of this repository. If
not, see <https://www.gnu.org/licenses/>.

## Installation

```
pip install poeminv
```

## Usage quick start

The library can be used to calculate ship emissions during movement (along
tracks) and mooring.

```
import pendulum
import poeminv

# The example config in this repository is valid, but only contains limited
# data for illustration.
config = poeminv.Config.from_yaml_path('config.example.yml')

# Suppose we have a bit of information about the ship, but some of it is
# missing. We can use the config to make an educated guess.
known_vessel_attributes = {
    'ship_type': 'container_ship', 'size': 4000, 'size_unit': 'teu',
    'year_of_build': 2001}
vessel_info = poeminv.VesselInfo(
    **config.guess_missing_vessel_info(**known_vessel_attributes))
print(vessel_info)  # VesselInfo(max_speed=25, engine_kw=37000, engine_rpm=100,
# engine_category='c3', engine_nox_tier=0, ship_type='container_ship',
# size=4000, size_unit='teu')

# Create the ship's track. Note that tide information is optional.
track = poeminv.Track.sanitized_from_positions([
    {
        'ts': 0, 'lon': 0, 'lat': 0, 'sog': 22.5, 'cog': 90, 'heading': 90,
        'tide_flow': 2, 'tide_bearing': 270},
    {
        'ts': 3600, 'lon': 0.33, 'lat': 0, 'sog': 20, 'cog': 90, 'heading': 90,
        'tide_flow': 2, 'tide_bearing': 270},
    {
        'ts': 7200, 'lon': 0.66, 'lat': 0, 'sog': 18, 'cog': 90, 'heading': 90,
        'tide_flow': 2, 'tide_bearing': 270},])
print(track.distance)  # 73388.49031698587 (meters)
print(track.duration)  # 2 hours

# We specified tide information, with which a speed through water (stw) is
# automatically calculated from speed over ground (sog). The library will use
# this when calculating engine load.
print(track.positions[0].sog, track.positions[0].stw)  # 22.5 24.5 (kts)

# The vessel-specific calculator calculates propulsion engine load along each
# segment of the track, gets estimates for auxiliary engine and boiler power
# from the config, and returns a dictionary of emissions (in grams) based on
# the expended energy.
calculator = poeminv.EmissionCalculator(config, vessel_info)
track_emissions = calculator.calculate_track_emissions(
    track, poeminv.Mode.TRANSIT)
print(track_emissions)  # {'nox': 1001500.8768000001, 'co2': 35536764.08934401}

# Mooring emissions don't need a track, only the time spent and which operating
# mode.
mooring_emissions = calculator.calculate_mooring_emissions(
    pendulum.duration(hours=20), poeminv.Mode.HOTELLING)
print(mooring_emissions)  # {'nox': 277440.0, 'co2': 21735397.6}
```

## The config file

Many details of the emission calculation must be configured in a `Config`,
including which pollutants are included and their emissionn factors, but also
data for guessing missing vessel information. This is done by loading a `.yml`
file like the `config.example.yml` in this repository. It must be a map
containing the keys

- `sea_margin_adjustment_factor`
- `base_values`
- `pollutants`
- `default_engine_powers`
- `vessel_info_guess_data`
- `average_vessel_build_times`
- `low_load_adjustment_factors`

### Sea margin

`sea_margin_adjustment_factor` is just a number that is multiplied with the
propulsion engine load calculated from speed to account for wind and waves.

### Match configs

The other keys contain lists of match configs in some form. These are objects
with a `match_criteria` key that specifies in which circumstances the config
applies (e.g. for oil tankers between 20000 and 80000 DWT), along with any
number of other keys that form the data of the config. Generally, these lists
are searched in the order in which they're defined, and data collected from all
matching configs until all needed keys are there (always using the first
occurence).

Keys in `match_criteria` objects can be `VesselInfo` attributes, but also any of
`engine_group`, `length`, `width`, `ais_type`, or `keel_laid_year`. The values
must be valid: `max_speed`, `engine_kw`, `engine_rpm`, `size`, `length`, and
`width` must be non-negative numbers. For `engine_category`, `engine_nox_tier`,
and `engine_group` the library exports enums with valid values. `ship_type` must
be a key in `poeminv.VALID_SHIP_TYPE_SIZE_UNITS`, which is a dictionary mapping
ship types to valid `size_unit`s for that ship type.

You can specify additional keys that can be used in match configs via
`Criterion.register_name()`.

Criteria can be specified in different ways:

- a constant, in which case the criterion matches if values are equal
- an object with keys `ge` (greater than or equal) and `lt` (less than) defining
  a range
- an object with key `any_of` mapping to a list of values that should match.

For example, the following match config matches if `engine_group` is
"propulsion", and 0 <= `engine_rpm` < 500 or `engine_rpm` is exactly 576.

```
match_criteria:
  engine_group: propulsion
  engine_rpm: {"any_of": [{"ge": 0, "lt": 500}, 576]}
data_item1: 10
data_item2: some_value
```

### Base values

`base_values` is a mapping where keys are names of substances that `pollutants`
are based on. Sometimes a base value will map to just one pollutant (like "nox"
in the example config), but sometimes a single base value can be used to derive
multiple ones (the example config derives "co2" from "bsfc" (brake-specific fuel
consumption), which other pollutants can also be based on).

Each key maps to a list of match configs, each of which must define a
`g_per_kwh` that specifies the amount of the substance in grams produced by
expending 1kWh of energy.

### Pollutants

`pollutants` defines which pollutants should be calculated and is similar in
structure to `base_values`. It is a list of match configs each of which must
have a `base_value_name` that is the name of one of the base values. Optionally,
they may have `multiplier` and `offset_g_per_kwh`, which must be numbers. The
value calculated for the pollutant is the offset plus the base value multiplier
by the multiplier. This allows you e.g. to derive multiple pollutants from
brake-specific fuel consumption.

### Default engine powers

`default_engine_powers` is used to get the power requirements of auxiliary
engines and boilers for different operating modes. Energy consumption from them
is included when calculating emissions for tracks. It is a list of match
configs, each of which must have the keys `transit`, `maneuvering`, `hotelling`,
and `anchorage`, specifying the power in that mode in kW. The `engine_group`
(auxiliary or boiler) must be specified via the `match_criteria`. For each
engine group, there must be a config without further criteria that can be used
as a fallback for ships where no entries match.

### Vessel info guess data

`vessel_info_guess_data` is used to create a full set of vessel info attributes
when only partial (or no) information is available. It is a list of match
configs, where the data contains any number of valid attributes used to
construct `VesselInfo` objects.

In the data, `ship_type`, `size`, and `size_unit` must always be specified
together to avoid nonsensical matchings of ship type and size.

Each attribute needed to create a `VesselInfo` object must be present in at
least one config that doesn't have any criteria (i.e. a fallback in case nothing
else matches). The easiest is to have one set of default values at the end.

For each possible ship type, there must be an object with no criteria other than
the ship type that specifies a `size` and `size_unit`. These are per-ship-type
default sizes. (In the example config, ship types with the same size units are
bunched together using `any_of` to make the config shorter, but this shouldn't
be done for a production config.)

It is recommended that for each ship type where size differences matter, there
are configs that make reasonable guesses for `size` and `size_unit` based on
length.

### Average vessel build times

`average_vessel_build_times` is used to derive a ship's keel-laid year from the
year of build, which can then be used to derive the engine's NOx tier (see
below). It is a list of match configs, each of which must specify a number
`build_time_years`.

### Low-load adjustment factors

`low_load_adjustment_factors` is used in emission calculation for propulsion
engines, to model them becoming less efficient at low loads. It is a list of
match configs, each with the single key `range_factors`. Each of those is a list
of objects with a `range` specifying a range of engine loads in [0, 1] in the
same format as in match criteria (i.e. via keys `ge` and `lt`), as well as a
`factors` map. This maps the name of pollutants (not base values) to an
adjustment factor.

For example, the following specifies that for engine loads between 0% and 10%
the final result of co2 emissions should be multiplied by 3, and for loads
between 10% and 20% by 2.

```
range_factors:
  - range: {"ge": 0, "lt": 0.1}
    factors:
      co2: 3
  - range: {"ge": 0.1, "lt": 0.2}
    factors:
      co2: 2
```

## NOx tier guessing

When guessing missing vessel information, there is some special handling around
the NOx tier since it is assumed that it's usually derived from
keel-laid year.

In cases where

- `engine_category` is 'c3'
- no `engine_nox_tier` is given
- no `keel_laid_year` is given
- `year_of_build` is given

`keel_laid_year` is derived using the average vessel build times described
above. This is then used to derive a (potentially more accurate)
`engine_nox_tier`.

## Tracks

Vessel movements are represented as `Track`s, which are sequences of `Position`s
along with some data regarding them. Each position has a `ts`, `lon`, `lat`,
`sog`, `cog` (speed and course over ground), `heading`, `tide_flow`,
`tide_bearing`, and `stw` (speed through water). `tide_flow` and `tide_bearing`
are optional (defaulting to no tide current), and `stw` is automatically
calculated from `sog` and the tide data.

Connections between positions are `Segment`s, which have a `distance` (in
meters) and a `duration`.

Tracks can be filled with positions using `append_position()`, but it is
recommended to use `Track.sanitized_from_positions()`, which accepts an iterable
of dictionaries representing positions. It accepts 2 functions
`sog_is_plausible` and `distance_covered_is_plausible` as arguments, which it
uses to do some sanitization:

- All positions that seem to be outliers based on the speed the vessel would
  have to have travelled are discarded outright.
- If the reported speed (`sog`) is missing, invalid, or seems implausibly high,
  it is replaced by a speed calculated from previous and following position.
- Similarly, if course and heading are missing or invalid, they are calculated
  as well.

The calculation of fuel and emissions does some additional adjustments where the
duration of segments along the track is needed, and duration and speed don't
match the length of the segment (not even roughly). In those cases, the
calculation pretends that the duration of the segment was actually higher or
lower, to get the data to be roughly consistent.

## Emission calculation

Emissions can be calculated for

- vessel movements using a track and a mode of operation (`TRANSIT` and
  `MANEUVERING`)
- moorings using a duration and a mode of operation (`HOTELLING` and
  `ANCHORAGE`)

All emissions are calculated based on energy in kWh using emission factors
mapping energy to pollutant mass in grams. These are derived from the
`pollutants` and `base_values` sections in the config. The `engine_group`
criterion in the relevant match configs is somewhat special, as it specifies
whether the value is to be used for propulsion, auxiliary, or boilers, rather
than some feature of the vessel.

Propulsion (i.e. main engine) energy is calculated using the track. For each
segment, the engine load is calculated via the propeller law using the vessel's
maximum speed and actual speed along that segment. The sea margin adjustment
factor is applied. Together with maximum rated engine power and duration of the
segment, this yields the total energy used.

Auxiliary engine and boiler energy is calculated using the configuration's
`default_engine_powers` and depends on the mode of operation. The appropriate
value is simply multiplied with the duration of the track or mooring.

## Testing

The library's test suite can be run in Docker without having to install any
dependencies using

```
docker-compose -f docker-compose.test.yml up --build
```
