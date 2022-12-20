# This file is part of edubot-matrix - https://github.com/openedtech/edubot-matrix
#
# edubot-matrix is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# edubot-matrix is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with edubot-matrix.  If not, see <http://www.gnu.org/licenses/>.
"""
Custom Types
"""
from datetime import datetime
from typing import TypedDict

from typing_extensions import NotRequired


class FeedInfo(TypedDict):
    name: NotRequired[str]
    url: str
    last_update: datetime


class FeedEntry(TypedDict):
    feed: FeedInfo
    url: str
    title: str
    description: str
