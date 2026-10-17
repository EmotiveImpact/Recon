"""Words that say what a business does rather than which business it is.

Matching leans on them: two salons sharing only "hair" and "Brighton" prove
nothing, and "Luxe Nails" and "Luxe Hair" next door are two businesses. Nothing
here is about any one trade. The words come from:

- trades.json, beside this file: trade words for many kinds of business,
  in groups;
- the target list: the words in its Overture categories, OpenStreetMap tags
  and sector names, and its own optional "trade_words" in the same shape as
  trades.json;
- the names in a run: a word in many of the names found ("salon" in a run of
  salons, "plumbing" in a run of plumbers) says little about which one.
"""

import collections
import json
import os
import re

from . import text

_TRADES_FILE = os.path.join(os.path.dirname(__file__), "trades.json")


def fold(word):
    """One spelling for plurals and possessives: "Barbers", "barber's" and
    "barber" are one word, as are "therapies" and "therapy"."""
    word = word.lower()
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("shes", "ches", "xes", "sses")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokens(name):
    """A name's words, folded, without company words like "Ltd" or "The"."""
    name = re.sub(r"[’'`]s\b", "", (name or "").lower())  # "Irini's" -> "irini".
    return [fold(w) for w in text.name_key(name).split()]


def _load_trades():
    if not hasattr(_load_trades, "groups"):
        with open(_TRADES_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        _load_trades.groups = {group: words for group, words in data.items()
                               if not group.startswith("_")}
    return _load_trades.groups


class Vocabulary:
    """Which words are trade words, and which trade each belongs to."""

    def __init__(self, target=None, names=(), common_share=0.02, common_min=5):
        self.group = {}  # word -> trade group, or "" for a trade word in no group.
        self.own = set()  # The trade groups the target is about; empty means all.
        for group, words in _load_trades().items():
            self._add(words, "" if group == "generic" else group)
        if target is not None:
            for group, words in (getattr(target, "trade_words", None) or {}).items():
                self._add(words, "" if group == "generic" else group)
                self.own.add("" if group == "generic" else group)
            described = [*target.overture_categories(), *target.sectors]
            described += [value for _, value in target.osm_tags()]
            for phrase in described:
                for word in re.split(r"[^a-z0-9]+", phrase.lower()):
                    if word and not word.isdigit():
                        self.own.add(self.group.setdefault(fold(word), ""))
            self.own.discard("")
        if names:
            counts = collections.Counter()
            for name in names:
                counts.update(set(tokens(name)))
            limit = max(common_min, common_share * len(names))
            for word, count in counts.items():
                if count >= limit and not word.isdigit():
                    self.group.setdefault(word, "")

    def _add(self, words, group):
        for word in words:
            for part in text.name_key(word).split():
                self.group[fold(part)] = group

    def is_trade(self, word):
        return fold(word) in self.group

    def is_own_trade(self, word):
        """A trade word of the target's own trades, or a word of no trade in
        particular. In a run of salons "Baker" in APRIL BAKER LTD is most
        likely a surname, so it counts as much as any other word."""
        group = self.group.get(fold(word))
        return group is not None and (not group or not self.own or group in self.own)

    def trades(self, words):
        """The trade groups a name's words point to."""
        return {self.group[w] for w in map(fold, words) if self.group.get(w)}

    def different_trades(self, words_a, words_b):
        trades_a, trades_b = self.trades(words_a), self.trades(words_b)
        return bool(trades_a and trades_b and not trades_a & trades_b)
