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

from poeminv.config import (
    Config,
    Range,
    VesselInfo,
    VALID_ENGINE_CATEGORIES,
    VALID_ENGINE_NOX_TIERS,
    VALID_ENGINE_GROUPS,
    VALID_SHIP_SIZE_UNITS,
    VALID_SHIP_TYPE_SIZE_UNITS,
)
from poeminv.emission import EmissionCalculator, SegmentDurationSanitizer
from poeminv.event import Mode, Position, Segment, Track
from poeminv.util import OpDict
