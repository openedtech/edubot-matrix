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
# along with edubot-matrix .  If not, see <http://www.gnu.org/licenses/>.


from edubot.bot import EduBot

from edubot_matrix.config import Config

edubot: EduBot | None = None

config: Config | None = None

POSITIVE_EMOJIS = [
    "๐ง",
    "๐",
    "โ",
    "๐",
    "๐ค",
    "๐",
    "๐",
    "๐",
    "โจ",
    "โ",
    "๐ค",
    "โ",
    "๐ค",
    "๐ฐ",
    "โค๏ธ",
    "๐ฏ" "๐",
    "๐",
    "๐",
    "๐",
    "๐",
    "๐คฃ",
    "๐",
    "๐",
    "๐",
    "๐ซ ",
    "๐",
    "๐",
    "๐",
    "๐ฅฐ",
    "๐",
]

NEGATIVE_EMOJIS = [
    "โ",
    "โ",
    "๐",
    "โ",
    "๐",
    "๐ซ",
    "๐ฉ",
    "๐",
    "๐ป",
    "๐",
    "โ",
    "๐",
    "๐",
    "๐คจ",
    "๐",
    "๐",
    "๐",
    "๐",
    "๐ฌ",
    "๐ต",
    "๐",
    "๐ซค",
    "๐",
    "๐",
    "โน",
    "๐ฎ",
    "๐ฏ",
    "๐ฒ",
    "๐ญ",
    "๐ข",
    "๐",
    "๐ก",
    "๐ ",
    "๐ค",
    "๐คฌ",
    "๐",
    "๐ฟ",
    "๐",
    "โ ",
    "๐ฉ",
    "๐คก",
    "๐น",
    "๐บ",
]
