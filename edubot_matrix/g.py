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
from re import Pattern, compile

from edubot.bot import EduBot

from edubot_matrix.config import Config

edubot: EduBot | None = None

config: Config | None = None

IMAGEGEN_REGEX: Pattern = compile(rf"(?i)(^.{0,25}?(imagine|draw))\s+(.*)")

POSITIVE_EMOJIS = [
    "🧘",
    "👍",
    "✌",
    "👌",
    "🤗",
    "🆗",
    "🌈",
    "💙",
    "✨",
    "➕",
    "🌤",
    "☘",
    "🤞",
    "🎰",
    "❤️",
    "💯" "😀",
    "😃",
    "😄",
    "😁",
    "😆",
    "🤣",
    "😂",
    "🙂",
    "🙃",
    "🫠",
    "😉",
    "😊",
    "😇",
    "🥰",
    "😍",
]

NEGATIVE_EMOJIS = [
    "⛔",
    "➖",
    "👎",
    "❌",
    "📉",
    "🚫",
    "🚩",
    "👎",
    "🏻",
    "🛑",
    "❓",
    "🙅",
    "🖕",
    "🤨",
    "😐",
    "😑",
    "😒",
    "🙄",
    "😬",
    "😵",
    "😕",
    "🫤",
    "😟",
    "🙁",
    "☹",
    "😮",
    "😯",
    "😲",
    "😭",
    "😢",
    "😞",
    "😡",
    "😠",
    "😤",
    "🤬",
    "😈",
    "👿",
    "💀",
    "☠",
    "💩",
    "🤡",
    "👹",
    "👺",
]
