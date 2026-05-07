from __future__ import annotations
import argparse, math, re
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter, sosfilt, butter as _butter

SR = 22050
_RNG = np.random.default_rng(42)

# ────────────────────────────────────────────────────────────────────────────
# Formant tables  (F1, F2, F3, F4)  all in Hz  — Peterson & Barney + Hillenbrand
# ────────────────────────────────────────────────────────────────────────────
VOWEL_F: Dict[str, Tuple[float,float,float,float]] = {
    "iy": ( 280, 2250, 3000, 3600),  # fleece
    "ih": ( 430, 1980, 2550, 3500),  # kit
    "ey": ( 400, 1900, 2500, 3400),  # face (mid-glide)
    "eh": ( 550, 1770, 2490, 3350),  # dress
    "ae": ( 660, 1720, 2410, 3300),  # trap
    "aa": ( 730, 1090, 2440, 3300),  # father
    "ah": ( 640, 1190, 2390, 3300),  # strut
    "ao": ( 560,  840, 2410, 3300),  # thought
    "uh": ( 460, 1105, 2735, 3300),  # foot
    "uw": ( 310,  870, 2250, 3200),  # goose
    "ow": ( 450,  750, 2400, 3300),  # goat (mid-glide)
    "ay": ( 660, 1700, 2530, 3300),  # price (onset)
    "aw": ( 660, 1100, 2530, 3300),  # mouth (onset)
    "oy": ( 490,  830, 2530, 3300),  # choice (onset)
    "er": ( 490, 1350, 1690, 3300),  # nurse / r-coloured
}
VOWEL_BW: Dict[str, Tuple[float,float,float,float]] = {
    k: (60, 80, 150, 200) for k in VOWEL_F
}
# Glide targets for diphthongs (where formants move TO)
DIPHTHONG_END: Dict[str, Tuple[float,float,float,float]] = {
    "ay": VOWEL_F["iy"],
    "aw": VOWEL_F["uw"],
    "oy": VOWEL_F["iy"],
    "ey": VOWEL_F["iy"],
    "ow": VOWEL_F["uw"],
}

# ────────────────────────────────────────────────────────────────────────────
# Consonant target formants for coarticulation transitions
# ────────────────────────────────────────────────────────────────────────────
CONSONANT_LOCUS: Dict[str, Tuple[float,float,float,float]] = {
    "p": ( 200,  800, 2300, 3300), "b": ( 200,  800, 2300, 3300),
    "t": ( 200, 1700, 2600, 3300), "d": ( 200, 1700, 2600, 3300),
    "k": ( 200, 1500, 2700, 3300), "g": ( 200, 1500, 2700, 3300),
    "m": ( 250,  900, 2200, 3300), "n": ( 250, 1700, 2600, 3300),
    "ng":( 250, 1500, 2500, 3300),
    "f": ( 350, 1300, 2000, 3300), "v": ( 350, 1300, 2000, 3300),
    "th":( 350, 1500, 2800, 3300), "dh":( 350, 1500, 2800, 3300),
    "s": ( 350, 1800, 2700, 4000), "z": ( 350, 1800, 2700, 4000),
    "sh":( 350, 1600, 2200, 3300), "zh":( 350, 1600, 2200, 3300),
    "ch":( 350, 1700, 2500, 3500), "j": ( 350, 1700, 2500, 3500),
    "l": ( 350, 1100, 2800, 3400), "r": ( 400,  900, 1400, 3300),
    "w": ( 250,  600, 2300, 3300), "y": ( 260, 2100, 2700, 3300),
    "h": ( 400, 1600, 2500, 3300),
}

# ────────────────────────────────────────────────────────────────────────────
# Greatly expanded G2P dictionary  (hand-verified common words)
# ────────────────────────────────────────────────────────────────────────────
DICT: Dict[str, List[str]] = {
    # articles / function words
    "the":["dh","ah"], "a":["ah"], "an":["ae","n"],
    "and":["ae","n","d"], "or":["ao","r"], "but":["b","ah","t"],
    "if":["ih","f"], "in":["ih","n"], "on":["ao","n"], "at":["ae","t"],
    "to":["t","uw"], "of":["ah","v"], "for":["f","ao","r"],
    "with":["w","ih","dh"], "as":["ae","z"], "by":["b","ay"],
    "from":["f","r","ah","m"], "into":["ih","n","t","uw"],
    "about":["ah","b","aw","t"], "after":["ae","f","t","er"],
    "before":["b","ih","f","ao","r"], "between":["b","ih","t","w","iy","n"],
    # pronouns
    "i":["ay"], "me":["m","iy"], "my":["m","ay"], "we":["w","iy"],
    "us":["ah","z"], "you":["y","uw"], "your":["y","ao","r"],
    "he":["h","iy"], "him":["h","ih","m"], "his":["h","ih","z"],
    "she":["sh","iy"], "her":["h","er"], "they":["dh","ey"],
    "them":["dh","eh","m"], "their":["dh","eh","r"],
    "it":["ih","t"], "its":["ih","t","s"], "this":["dh","ih","s"],
    "that":["dh","ae","t"], "these":["dh","iy","z"], "those":["dh","ow","z"],
    # common verbs
    "is":["ih","z"], "are":["aa","r"], "was":["w","ah","z"],
    "were":["w","er"], "be":["b","iy"], "been":["b","iy","n"],
    "have":["h","ae","v"], "has":["h","ae","z"], "had":["h","ae","d"],
    "do":["d","uw"], "does":["d","ah","z"], "did":["d","ih","d"],
    "will":["w","ih","l"], "would":["w","uh","d"], "shall":["sh","ae","l"],
    "should":["sh","uh","d"], "may":["m","ey"], "might":["m","ay","t"],
    "can":["k","ae","n"], "could":["k","uh","d"],
    "go":["g","ow"], "get":["g","eh","t"], "got":["g","ao","t"],
    "come":["k","ah","m"], "came":["k","ey","m"],
    "make":["m","ey","k"], "made":["m","ey","d"],
    "see":["s","iy"], "saw":["s","ao"],
    "say":["s","ey"], "said":["s","eh","d"],
    "know":["n","ow"], "knew":["n","uw"],
    "think":["th","ih","ng","k"], "thought":["th","ao","t"],
    "take":["t","ey","k"], "took":["t","uh","k"],
    "give":["g","ih","v"], "gave":["g","ey","v"],
    "look":["l","uh","k"], "looked":["l","uh","k","t"],
    "want":["w","ao","n","t"], "need":["n","iy","d"],
    "use":["y","uw","z"], "find":["f","ay","n","d"],
    "tell":["t","eh","l"], "feel":["f","iy","l"],
    "try":["t","r","ay"], "leave":["l","iy","v"],
    "call":["k","ao","l"], "keep":["k","iy","p"],
    "let":["l","eh","t"], "begin":["b","ih","g","ih","n"],
    "show":["sh","ow"], "seem":["s","iy","m"],
    "help":["h","eh","l","p"], "turn":["t","er","n"],
    "start":["s","t","aa","r","t"], "move":["m","uw","v"],
    "play":["p","l","ey"], "run":["r","ah","n"],
    "live":["l","ih","v"], "hold":["h","ow","l","d"],
    "bring":["b","r","ih","ng"], "happen":["h","ae","p","ah","n"],
    "write":["r","ay","t"], "provide":["p","r","ah","v","ay","d"],
    "sit":["s","ih","t"], "stand":["s","t","ae","n","d"],
    "lose":["l","uw","z"], "pay":["p","ey"],
    "meet":["m","iy","t"], "include":["ih","n","k","l","uw","d"],
    "continue":["k","ah","n","t","ih","n","y","uw"],
    "set":["s","eh","t"], "learn":["l","er","n"],
    "change":["ch","ey","n","j"], "lead":["l","iy","d"],
    "understand":["ah","n","d","er","s","t","ae","n","d"],
    "watch":["w","ao","ch"], "follow":["f","ao","l","ow"],
    "stop":["s","t","ao","p"], "create":["k","r","iy","ey","t"],
    "speak":["s","p","iy","k"], "read":["r","iy","d"],
    "spend":["s","p","eh","n","d"], "grow":["g","r","ow"],
    "open":["ow","p","ah","n"], "walk":["w","ao","k"],
    "win":["w","ih","n"], "offer":["ao","f","er"],
    "remember":["r","ih","m","eh","m","b","er"],
    "love":["l","ah","v"], "consider":["k","ah","n","s","ih","d","er"],
    "appear":["ah","p","ih","r"], "buy":["b","ay"],
    "wait":["w","ey","t"], "serve":["s","er","v"],
    "die":["d","ay"], "send":["s","eh","n","d"],
    "expect":["ih","k","s","p","eh","k","t"],
    "build":["b","ih","l","d"], "stay":["s","t","ey"],
    "fall":["f","ao","l"], "cut":["k","ah","t"],
    "reach":["r","iy","ch"], "kill":["k","ih","l"],
    "remain":["r","ih","m","ey","n"], "suggest":["s","ah","g","j","eh","s","t"],
    "raise":["r","ey","z"], "pass":["p","ae","s"],
    "sell":["s","eh","l"], "require":["r","ih","k","w","ay","er"],
    "report":["r","ih","p","ao","r","t"],
    "decide":["d","ih","s","ay","d"],
    "pull":["p","uh","l"], "push":["p","uh","sh"],
    # common nouns
    "time":["t","ay","m"], "year":["y","ih","r"],
    "people":["p","iy","p","ah","l"], "way":["w","ey"],
    "day":["d","ey"], "man":["m","ae","n"], "woman":["w","uh","m","ah","n"],
    "child":["ch","ay","l","d"], "world":["w","er","l","d"],
    "life":["l","ay","f"], "hand":["h","ae","n","d"],
    "part":["p","aa","r","t"], "place":["p","l","ey","s"],
    "case":["k","ey","s"], "week":["w","iy","k"],
    "company":["k","ah","m","p","ah","n","iy"],
    "system":["s","ih","s","t","ah","m"],
    "program":["p","r","ow","g","r","ae","m"],
    "question":["k","w","eh","s","ch","ah","n"],
    "work":["w","er","k"], "government":["g","ah","v","er","n","m","ah","n","t"],
    "number":["n","ah","m","b","er"], "night":["n","ay","t"],
    "point":["p","oy","n","t"], "city":["s","ih","t","iy"],
    "home":["h","ow","m"], "water":["w","ao","t","er"],
    "room":["r","uw","m"], "mother":["m","ah","dh","er"],
    "area":["eh","r","iy","ah"], "money":["m","ah","n","iy"],
    "story":["s","t","ao","r","iy"], "fact":["f","ae","k","t"],
    "month":["m","ah","n","th"], "lot":["l","ao","t"],
    "right":["r","ay","t"], "study":["s","t","ah","d","iy"],
    "book":["b","uh","k"], "eye":["ay"],
    "job":["j","ao","b"], "word":["w","er","d"],
    "business":["b","ih","z","n","ah","s"],
    "issue":["ih","sh","uw"], "side":["s","ay","d"],
    "kind":["k","ay","n","d"], "head":["h","eh","d"],
    "house":["h","aw","s"], "service":["s","er","v","ih","s"],
    "friend":["f","r","eh","n","d"], "father":["f","aa","dh","er"],
    "power":["p","aw","er"], "hour":["aw","er"],
    "game":["g","ey","m"], "line":["l","ay","n"],
    "end":["eh","n","d"], "among":["ah","m","ah","ng"],
    "car":["k","aa","r"], "city":["s","ih","t","iy"],
    "community":["k","ah","m","y","uw","n","ah","t","iy"],
    "name":["n","ey","m"], "president":["p","r","eh","z","ih","d","ah","n","t"],
    "team":["t","iy","m"], "minute":["m","ih","n","ah","t"],
    "air":["eh","r"], "sea":["s","iy"],
    "ground":["g","r","aw","n","d"], "form":["f","ao","r","m"],
    "body":["b","ao","d","iy"], "law":["l","ao"],
    # adjectives/adverbs
    "good":["g","uh","d"], "new":["n","uw"], "first":["f","er","s","t"],
    "last":["l","ae","s","t"], "long":["l","ao","ng"],
    "great":["g","r","ey","t"], "little":["l","ih","t","ah","l"],
    "own":["ow","n"], "other":["ah","dh","er"],
    "old":["ow","l","d"], "large":["l","aa","r","j"],
    "big":["b","ih","g"], "small":["s","m","ao","l"],
    "high":["h","ay"], "low":["l","ow"],
    "next":["n","eh","k","s","t"], "early":["er","l","iy"],
    "young":["y","ah","ng"], "important":["ih","m","p","ao","r","t","ah","n","t"],
    "public":["p","ah","b","l","ih","k"],
    "private":["p","r","ay","v","ah","t"],
    "real":["r","iy","ah","l"], "best":["b","eh","s","t"],
    "free":["f","r","iy"], "sure":["sh","uh","r"],
    "far":["f","aa","r"], "hard":["h","aa","r","d"],
    "near":["n","ih","r"], "past":["p","ae","s","t"],
    "late":["l","ey","t"], "true":["t","r","uw"],
    "whole":["h","ow","l"], "clear":["k","l","ih","r"],
    "dark":["d","aa","r","k"], "white":["w","ay","t"],
    "black":["b","l","ae","k"], "red":["r","eh","d"],
    "blue":["b","l","uw"], "green":["g","r","iy","n"],
    # question words / common advs
    "very":["v","eh","r","iy"], "just":["j","ah","s","t"],
    "also":["ao","l","s","ow"], "back":["b","ae","k"],
    "only":["ow","n","l","iy"], "still":["s","t","ih","l"],
    "over":["ow","v","er"], "even":["iy","v","ah","n"],
    "well":["w","eh","l"], "never":["n","eh","v","er"],
    "here":["h","ih","r"], "there":["dh","eh","r"],
    "now":["n","aw"], "then":["dh","eh","n"],
    "how":["h","aw"], "when":["w","eh","n"],
    "where":["w","eh","r"], "what":["w","ah","t"],
    "who":["h","uw"], "which":["w","ih","ch"],
    "why":["w","ay"], "more":["m","ao","r"],
    "most":["m","ow","s","t"], "much":["m","ah","ch"],
    "many":["m","eh","n","iy"], "some":["s","ah","m"],
    "any":["eh","n","iy"], "both":["b","ow","th"],
    "each":["iy","ch"], "all":["ao","l"],
    "no":["n","ow"], "not":["n","ao","t"],
    "yes":["y","eh","s"], "up":["ah","p"],
    "down":["d","aw","n"], "out":["aw","t"],
    "same":["s","ey","m"], "different":["d","ih","f","er","ah","n","t"],
    "few":["f","y","uw"], "through":["th","r","uw"],
    "after":["ae","f","t","er"], "again":["ah","g","eh","n"],
    "against":["ah","g","eh","n","s","t"],
    "already":["ao","l","r","eh","d","iy"],
    "always":["ao","l","w","ey","z"],
    "around":["ah","r","aw","n","d"],
    "away":["ah","w","ey"], "bad":["b","ae","d"],
    "beautiful":["b","y","uw","t","ah","f","ah","l"],
    "because":["b","ih","k","ao","z"],
    "between":["b","ih","t","w","iy","n"],
    "off":["ao","f"], "often":["ao","f","ah","n"],
    "once":["w","ah","n","s"], "only":["ow","n","l","iy"],
    "else":["eh","l","s"], "every":["eh","v","r","iy"],
    "example":["ih","g","z","ae","m","p","ah","l"],
    "general":["j","eh","n","er","ah","l"],
    "hello":["h","ah","l","ow"], "hi":["h","ay"],
    "hey":["h","ey"], "ok":["ow","k","ey"],
    "okay":["ow","k","ey"], "yes":["y","eh","s"],
    "yeah":["y","ae"], "nah":["n","aa"],
    "please":["p","l","iy","z"],
    "thank":["th","ae","ng","k"], "thanks":["th","ae","ng","k","s"],
    "sorry":["s","ao","r","iy"], "welcome":["w","eh","l","k","ah","m"],
    "quick":["k","w","ih","k"], "brown":["b","r","aw","n"],
    "fox":["f","ao","k","s"], "jumps":["j","ah","m","p","s"],
    "lazy":["l","ey","z","iy"], "dog":["d","ao","g"],
    "the":["dh","ah"], "over":["ow","v","er"],
    "future":["f","y","uw","ch","er"],
    "speech":["s","p","iy","ch"],
    "sound":["s","aw","n","d"], "voice":["v","oy","s"],
    "language":["l","ae","ng","g","w","ah","j"],
    "computer":["k","ah","m","p","y","uw","t","er"],
    "human":["h","y","uw","m","ah","n"],
    "natural":["n","ae","ch","er","ah","l"],
    "quality":["k","w","ao","l","ah","t","iy"],
    "better":["b","eh","t","er"], "worse":["w","er","s"],
    "perfect":["p","er","f","ih","k","t"],
    "simple":["s","ih","m","p","ah","l"],
    "test":["t","eh","s","t"], "audio":["ao","d","iy","ow"],
    "music":["m","y","uw","z","ih","k"],
    "sing":["s","ih","ng"], "song":["s","ao","ng"],
    "listen":["l","ih","s","ah","n"],
    "hear":["h","ih","r"], "ear":["ih","r"],
    "nice":["n","ay","s"], "cool":["k","uw","l"],
    "warm":["w","ao","r","m"], "cold":["k","ow","l","d"],
    "hot":["h","ao","t"],
}

ALL_VOWELS = set(VOWEL_F.keys())
ALL_CONSONANTS = set(CONSONANT_LOCUS.keys())

# ────────────────────────────────────────────────────────────────────────────
# Rule-based G2P for out-of-dictionary words
# ────────────────────────────────────────────────────────────────────────────
_DIGRAPH = {
    "ch":"ch","sh":"sh","th":"th","ng":"ng","gh":"",
    "ph":"f","wh":"w","ck":"k","qu":"kw","wr":"r",
    "kn":"n","gn":"n","mn":"n","ps":"s",
}

def _g2p_rules(word: str) -> List[str]:
    phones: List[str] = []
    i = 0
    w = word.lower()
    n = len(w)
    while i < n:
        c = w[i]
        # 4-char sequences first
        if i+3 < n:
            quad = w[i:i+4]
            if quad == "tion":   # nation, station → sh+ah+n
                phones.extend(["sh","ah","n"]); i+=4; continue
            if quad == "sion":   # vision, passion → zh+ah+n
                phones.extend(["zh","ah","n"]); i+=4; continue
        # 3-char sequences
        if i+2 < n:
            tri = w[i:i+3]
            if tri == "ion":     # ion, ions → ay+ah+n
                phones.extend(["ay","ah","n"]); i+=3; continue
        # 2-char digraph check
        if i+1 < n:
            dg = w[i:i+2]
            if dg in _DIGRAPH:
                p = _DIGRAPH[dg]
                if p:
                    phones.append(p)
                i += 2
                continue
        # vowels
        if c in "aeiou":
            # simple rules
            if c == 'a':
                if i+1<n and w[i+1]=='e' and i+2==n:  phones.append("ey"); i+=2; continue
                if i+1<n and w[i+1]=='i':              phones.append("ey"); i+=2; continue
                if i+1<n and w[i+1]=='y':              phones.append("ey"); i+=2; continue
                if i+1<n and w[i+1]=='o':              phones.append("ao"); i+=2; continue
                if i+1<n and w[i+1]=='u':              phones.append("ao"); i+=2; continue
                # silent final e
                if i+2<n and w[i+1] not in "aeiou" and w[i+2]=='e' and i+3==n:
                    phones.append("ey"); i+=1; continue
                phones.append("ae"); i+=1; continue
            elif c == 'e':
                if i == n-1: i+=1; continue  # silent final e
                if i+1<n and w[i+1]=='e':              phones.append("iy"); i+=2; continue
                if i+1<n and w[i+1]=='a':              phones.append("iy"); i+=2; continue
                if i+1<n and w[i+1]=='i':              phones.append("ey"); i+=2; continue
                if i+1<n and w[i+1]=='w':              phones.append("uw"); i+=2; continue
                phones.append("eh"); i+=1; continue
            elif c == 'i':
                if i+1<n and w[i+1]=='e':              phones.append("ay"); i+=2; continue
                # "io" → iy + ow as two separate sounds (radio, audio, ratio, ion)
                # do NOT consume the 'o' here; let the next iteration handle it
                if i+1<n and w[i+1]=='o':              phones.append("iy"); i+=1; continue
                # silent final e pattern
                if i+2<n and w[i+1] not in "aeiou" and w[i+2]=='e' and i+3==n:
                    phones.append("ay"); i+=1; continue
                phones.append("ih"); i+=1; continue
            elif c == 'o':
                if i+1<n and w[i+1]=='o':              phones.append("uw"); i+=2; continue
                if i+1<n and w[i+1]=='e' and i+2==n:  phones.append("ow"); i+=2; continue
                if i+1<n and w[i+1]=='a':              phones.append("ow"); i+=2; continue
                if i+1<n and w[i+1]=='w':              phones.append("ow"); i+=2; continue
                if i+1<n and w[i+1]=='i':              phones.append("oy"); i+=2; continue
                if i+1<n and w[i+1]=='u':              phones.append("aw"); i+=2; continue
                if i+1<n and w[i+1] not in "aeiou" and i+2<n and w[i+2] not in "aeiou":
                    phones.append("ao"); i+=1; continue
                phones.append("ow"); i+=1; continue
            elif c == 'u':
                if i+1<n and w[i+1]=='e':              phones.append("uw"); i+=2; continue
                if i+1<n and w[i+1]=='i':              phones.append("uw"); i+=2; continue
                if i+1<n and w[i+1]=='o':              phones.append("uw"); i+=2; continue
                phones.append("ah"); i+=1; continue
        elif c == 'y':
            if i == 0:
                phones.append("y"); i+=1; continue
            if i == n-1 or (i+1 < n and w[i+1] not in "aeiou"):
                phones.append("iy"); i+=1; continue
            phones.append("ih"); i+=1; continue
        elif c == 'c':
            if i+1<n and w[i+1] in "ei":  phones.append("s")
            else:                           phones.append("k")
            i+=1; continue
        elif c == 'g':
            if i+1<n and w[i+1] in "ei":  phones.append("j")
            else:                           phones.append("g")
            i+=1; continue
        elif c == 'x':
            phones.extend(["k","s"]); i+=1; continue
        elif c == 's':
            # intervocalic s → z
            if i>0 and i+1<n and w[i-1] in "aeiou" and w[i+1] in "aeiou":
                phones.append("z")
            else:
                phones.append("s")
            i+=1; continue
        elif c in "bdfjklmnprvwz":
            phones.append(c); i+=1; continue
        elif c == 'h':
            if i+1<n and w[i+1] not in "aeiou": i+=1; continue  # silent h
            phones.append("h"); i+=1; continue
        elif c == 'q':
            phones.extend(["k","w"]); i+=1
            if i<n and w[i]=='u': i+=1
            continue
        elif c == 't':
            if i+1<n and w[i+1]=='i' and i+2<n and w[i+2] in "ao":
                phones.append("sh"); i+=1; continue
            phones.append("t"); i+=1; continue
        elif c in "'-":
            i+=1; continue
        else:
            i+=1; continue
    return phones

# Contraction expansions → phoneme sequences directly
_CONTRACTIONS: Dict[str, List[str]] = {
    "i'm":    ["ay","m"],
    "i'll":   ["ay","l"],
    "i've":   ["ay","v"],
    "i'd":    ["ay","d"],
    "you're": ["y","uw","r"],
    "you'll": ["y","uw","l"],
    "you've": ["y","uw","v"],
    "you'd":  ["y","uw","d"],
    "he's":   ["h","iy","z"],
    "he'll":  ["h","iy","l"],
    "he'd":   ["h","iy","d"],
    "she's":  ["sh","iy","z"],
    "she'll": ["sh","iy","l"],
    "she'd":  ["sh","iy","d"],
    "we're":  ["w","iy","r"],
    "we'll":  ["w","iy","l"],
    "we've":  ["w","iy","v"],
    "we'd":   ["w","iy","d"],
    "they're":["dh","ey","r"],
    "they'll":["dh","ey","l"],
    "they've":["dh","ey","v"],
    "they'd": ["dh","ey","d"],
    "it's":  ["ih","t","s"],
    "it'll": ["ih","t","ah","l"],
    "that's":["dh","ae","t","s"],
    "there's":["dh","eh","r","z"],
    "here's":["h","ih","r","z"],
    "what's":["w","ah","t","s"],
    "who's": ["h","uw","z"],
    "don't": ["d","ow","n","t"],
    "doesn't":["d","ah","z","ah","n","t"],
    "didn't":["d","ih","d","ah","n","t"],
    "won't":  ["w","ow","n","t"],
    "wouldn't":["w","uh","d","ah","n","t"],
    "shouldn't":["sh","uh","d","ah","n","t"],
    "couldn't":["k","uh","d","ah","n","t"],
    "can't":  ["k","ae","n","t"],
    "isn't":  ["ih","z","ah","n","t"],
    "aren't": ["aa","r","ah","n","t"],
    "wasn't": ["w","ah","z","ah","n","t"],
    "weren't":["w","er","ah","n","t"],
    "hasn't": ["h","ae","z","ah","n","t"],
    "haven't":["h","ae","v","ah","n","t"],
    "hadn't": ["h","ae","d","ah","n","t"],
    "let's":  ["l","eh","t","s"],
    "how's":  ["h","aw","z"],
    "when's": ["w","eh","n","z"],
    "where's":["w","eh","r","z"],
    "why's":  ["w","ay","z"],
}

def word_to_phones(word: str) -> List[str]:
    w = word.lower()
    # Check contractions first (before stripping apostrophes)
    if w in _CONTRACTIONS:
        return list(_CONTRACTIONS[w])
    # Strip punctuation for dict/rules lookup
    w = w.strip("\''.,-")
    if not w: return []
    if w in DICT: return list(DICT[w])
    return _g2p_rules(w)

# ────────────────────────────────────────────────────────────────────────────
# Phoneme sequence with prosody
# ────────────────────────────────────────────────────────────────────────────
PAUSE_LONG  = "<P>"   # sentence boundary
PAUSE_SHORT = "<p>"   # comma/clause
PAUSE_WORD  = "<w>"   # inter-word

def text_to_phones(text: str) -> List[Tuple[str, bool, bool]]:
    """Returns list of (phoneme, stressed, word_final)"""
    text = text.strip()
    tokens = re.findall(r"[a-z0-9''-]+|[.,!?;:]", text.lower())

    result: List[Tuple[str,bool,bool]] = []
    for tok in tokens:
        if tok in ".!?":
            result.append((PAUSE_LONG, False, False)); continue
        if tok in ",;:":
            result.append((PAUSE_SHORT, False, False)); continue

        phones = word_to_phones(tok)
        if not phones: continue

        # Mark first vowel as (primary) stressed
        stressed_idx = next((i for i,p in enumerate(phones) if p in ALL_VOWELS), None)

        for i, ph in enumerate(phones):
            is_stressed = (i == stressed_idx)
            is_final    = (i == len(phones)-1)
            result.append((ph, is_stressed, is_final))
        result.append((PAUSE_WORD, False, False))

    # Trim trailing pauses
    while result and result[-1][0] in (PAUSE_WORD, PAUSE_SHORT, PAUSE_LONG):
        result.pop()
    return result

# ────────────────────────────────────────────────────────────────────────────
# DSP helpers
# ────────────────────────────────────────────────────────────────────────────
def _butter_sos(ftype, cutoff, order=4):
    nyq = SR / 2
    if isinstance(cutoff, (list, tuple)):
        wn = [c/nyq for c in cutoff]
    else:
        wn = cutoff / nyq
    wn = np.clip(wn, 1e-4, 0.9999)
    return butter(order, wn, btype=ftype, output='sos')

def lpf(x, fc, order=4):
    return sosfilt(_butter_sos('low', fc, order), x).astype(np.float32)

def hpf(x, fc, order=2):
    return sosfilt(_butter_sos('high', fc, order), x).astype(np.float32)

def bpf(x, lo, hi, order=3):
    lo = max(30, lo); hi = min(hi, SR/2 - 100)
    if lo >= hi: return x
    return sosfilt(_butter_sos('band', [lo,hi], order), x).astype(np.float32)

def _ramp(n, kind='lin'):
    if kind == 'sq':  return np.sqrt(np.linspace(0,1,n,dtype=np.float32))
    if kind == 'sq2': return (np.linspace(0,1,n,dtype=np.float32))**2
    return np.linspace(0,1,n,dtype=np.float32)

# ────────────────────────────────────────────────────────────────────────────
# LF (Liljencrants-Fant) glottal pulse  — much more realistic than sine harmonics
# ────────────────────────────────────────────────────────────────────────────
def _lf_pulse(n_samples: int) -> np.ndarray:
    """Single normalised LF glottal pulse, unit length"""
    t = np.linspace(0, 1, n_samples, endpoint=False, dtype=np.float64)
    Ee = 1.0; Tp = 0.40; Te = 0.72; Ta = 0.06
    Tb = 1.0 - Te
    alpha = 3.0  # glottal opening slope

    out = np.zeros(n_samples, dtype=np.float64)
    open_phase = t < Te
    out[open_phase] = np.exp(alpha * t[open_phase]) * np.sin(np.pi * t[open_phase] / Te) / np.exp(alpha * Te)

    close = ~open_phase
    t_close = t[close] - Te
    eps = 1.0 / (Ta * 100) if Ta > 0 else 100.0
    out[close] = -Ee / (eps * Ta) * (np.exp(-eps * t_close) - np.exp(-eps * Tb))

    # differentiate (flow → pressure)
    out = np.diff(out, prepend=out[0])
    # normalize
    pk = np.max(np.abs(out))
    if pk > 0: out /= pk
    return out.astype(np.float32)

_LF_CACHE: Dict[int, np.ndarray] = {}

def glottal_source(f0_contour: np.ndarray, breathiness: float = 0.10) -> np.ndarray:
    """Generate voiced excitation from F0 contour using LF pulses"""
    n = len(f0_contour)
    out = np.zeros(n, dtype=np.float32)
    pos = 0
    while pos < n:
        f0 = float(f0_contour[min(pos, n-1)])
        period = int(round(SR / max(f0, 50)))
        period = max(period, 16)

        if period not in _LF_CACHE:
            _LF_CACHE[period] = _lf_pulse(period)
        pulse = _LF_CACHE[period]

        end = min(pos + period, n)
        plen = end - pos
        out[pos:end] += pulse[:plen]
        pos += period

    # add breathiness noise
    if breathiness > 0:
        noise = _RNG.standard_normal(n).astype(np.float32)
        noise = lpf(noise, 4000, 2)
        out += breathiness * noise

    # normalize
    pk = np.max(np.abs(out))
    if pk > 0: out /= pk
    return out

# ────────────────────────────────────────────────────────────────────────────
# Klatt parallel formant bank
# ────────────────────────────────────────────────────────────────────────────
def _one_formant_sos(fc: float, bw: float, gain_db: float = 0.0) -> np.ndarray:
    """Second-order resonator (parallel bank branch)"""
    w0 = 2 * np.pi * fc / SR
    bw_r = 2 * np.pi * bw / SR
    r = np.exp(-bw_r / 2)
    cos_w = np.cos(w0)
    b0 = (1 - r*r) / 2  # amplitude normalised
    gain = 10 ** (gain_db / 20)
    b = np.array([b0 * gain, 0, -b0 * gain], dtype=np.float64)
    a = np.array([1, -2*r*cos_w, r*r], dtype=np.float64)
    sos = np.array([[b[0], b[1], b[2], a[0], a[1], a[2]]])
    return sos

def parallel_formant_synth(src: np.ndarray,
                            formants: List[Tuple[float,float]],
                            gains_db: Optional[List[float]] = None) -> np.ndarray:
    """Sum parallel resonators — avoids spectral smearing of cascade filters"""
    if gains_db is None:
        gains_db = [0.0, -3.0, -6.0, -12.0]
    out = np.zeros(len(src), dtype=np.float32)
    for i, (fc, bw) in enumerate(formants):
        fc = float(np.clip(fc, 50, SR/2 - 100))
        bw = float(np.clip(bw, 30, 800))
        gdb = gains_db[i] if i < len(gains_db) else -12.0
        sos = _one_formant_sos(fc, bw, gdb)
        branch = sosfilt(sos, src.astype(np.float64)).astype(np.float32)
        out += branch
    return out

# ────────────────────────────────────────────────────────────────────────────
# Phoneme durations (seconds)
# ────────────────────────────────────────────────────────────────────────────
_DUR: Dict[str, float] = {
    "iy":0.115,"ih":0.090,"ey":0.130,"eh":0.095,"ae":0.115,
    "aa":0.155,"ah":0.105,"ao":0.140,"uh":0.090,"uw":0.120,
    "ow":0.135,"ay":0.150,"aw":0.150,"oy":0.145,"er":0.130,
    "p":0.055,"b":0.060,"t":0.060,"d":0.065,"k":0.075,"g":0.075,
    "f":0.085,"v":0.080,"th":0.090,"dh":0.085,
    "s":0.100,"z":0.090,"sh":0.105,"zh":0.100,"h":0.055,
    "ch":0.110,"j":0.110,
    "m":0.085,"n":0.080,"ng":0.085,
    "l":0.070,"r":0.075,"w":0.060,"y":0.055,
}

def phoneme_dur(ph: str, stressed: bool, speed: float) -> int:
    base = _DUR.get(ph, 0.08)
    if ph in ALL_VOWELS and stressed:
        base *= 1.35
    return max(1, int(base * SR / speed))

# ────────────────────────────────────────────────────────────────────────────
# F0 model
# ────────────────────────────────────────────────────────────────────────────
_BASE_F0 = 118.0  # Hz  (natural male voice)

def f0_contour(n: int, stressed: bool, phrase_pos: float) -> np.ndarray:
    """
    phrase_pos: 0=start … 1=end of utterance  (for declination)
    """
    t = np.linspace(0, 1, n, dtype=np.float32)
    # Declination: pitch falls ~12 Hz over the utterance
    declination = _BASE_F0 * (1 - 0.10 * phrase_pos)

    if stressed:
        pitch = declination + 10 * np.sin(np.pi * t)
    else:
        pitch = declination - 4 + 3 * t

    # micro-variation (shimmer / jitter sim)
    pitch += 1.2 * np.sin(2*np.pi*5.1*t) + 0.8 * np.sin(2*np.pi*7.3*t)
    return np.clip(pitch, 60, 400).astype(np.float32)

# ────────────────────────────────────────────────────────────────────────────
# Per-phoneme synthesis with coarticulation
# ────────────────────────────────────────────────────────────────────────────

def _formant_interp(f_start, f_end, n, curve='sqrt'):
    """Smooth formant trajectory from start to end"""
    t = np.linspace(0, 1, n, dtype=np.float32)
    if curve == 'sqrt': t = np.sqrt(t)
    return [(f_start[i] + (f_end[i]-f_start[i])*t) for i in range(len(f_start))]

def synth_vowel(ph: str, n: int, f0: np.ndarray,
                f_prev: Optional[Tuple], f_next: Optional[Tuple]) -> np.ndarray:
    fv = VOWEL_F[ph]
    bv = VOWEL_BW.get(ph, (60,80,150,200))

    # Formant trajectories with coarticulation
    trans_frac = 0.20  # 20% of duration for transitions
    trans_n = max(1, int(n * trans_frac))

    # Build time-varying formant arrays
    F = [np.full(n, fv[i], dtype=np.float32) for i in range(4)]

    # Onset transition from previous context
    if f_prev:
        for i in range(4):
            F[i][:trans_n] = np.linspace(f_prev[i], fv[i], trans_n, dtype=np.float32)

    # Offset transition to next context
    if f_next:
        for i in range(4):
            F[i][-trans_n:] = np.linspace(fv[i], f_next[i], trans_n, dtype=np.float32)

    # Diphthong glide
    if ph in DIPHTHONG_END:
        f_end = DIPHTHONG_END[ph]
        glide_start = int(n * 0.45)
        for i in range(4):
            F[i][glide_start:] = np.linspace(fv[i], f_end[i], n-glide_start, dtype=np.float32)

    # Glottal source
    src = glottal_source(f0, breathiness=0.08)

    # Apply pre-emphasis (simulate lip radiation)
    src = np.diff(src, prepend=src[:1]) * 0.98 + src

    # Parallel formant bank — use time-varying formants by splitting into frames
    FRAME = 64
    out = np.zeros(n, dtype=np.float32)
    for start in range(0, n, FRAME):
        end = min(start+FRAME, n)
        chunk = src[start:end]
        fc = [float(F[i][(start+end)//2]) for i in range(4)]
        bw = list(bv)
        gains = [0.0, -4.0, -8.0, -15.0]
        out[start:end] = parallel_formant_synth(chunk, list(zip(fc,bw)), gains)

    # Amplitude envelope
    atk = max(1, int(n * 0.08))
    rel = max(1, int(n * 0.18))
    env = np.ones(n, dtype=np.float32)
    env[:atk]  = _ramp(atk,'sq')
    env[-rel:]  = _ramp(rel,'sq')[::-1]
    out *= env

    # Normalize
    pk = np.max(np.abs(out))
    if pk > 0: out *= 0.88 / pk
    return out

def synth_fricative(ph: str, n: int, voiced_f0: Optional[np.ndarray] = None) -> np.ndarray:
    noise = _RNG.standard_normal(n).astype(np.float32)

    bands = {
        "s": (4500, 10000, 0.32), "z": (3500, 9000, 0.22),
        "sh":(1800, 5500, 0.28), "zh":(1800, 5500, 0.20),
        "f": (1200, 7000, 0.24), "v": (1000, 6000, 0.16),
        "th":(1400, 7500, 0.20), "dh":(1200, 6500, 0.14),
        "h": (500,  4000, 0.22),
    }
    lo, hi, amp = bands.get(ph, (1000, 6000, 0.20))
    noise = bpf(noise, lo, hi, order=2)

    # Amplitude envelope
    atk = max(1, int(n*0.08))
    rel = max(1, int(n*0.25))
    env = np.ones(n, dtype=np.float32)
    env[:atk] = _ramp(atk)
    env[-rel:] = _ramp(rel)[::-1]
    out = amp * noise * env

    # Add voicing
    if ph in {"v","z","zh","dh"} and voiced_f0 is not None:
        f0_trim = voiced_f0[:n]
        vo = glottal_source(f0_trim, 0.0)
        if len(vo) < n: vo = np.pad(vo, (0, n - len(vo)))
        vo = vo[:n]
        vo = lpf(vo, 1800, 2)
        out += 0.25 * vo * env

    return out

def synth_stop(ph: str, n: int, voiced_f0: Optional[np.ndarray] = None) -> np.ndarray:
    closure = max(1, int(n * 0.45))
    burst_n  = n - closure

    # Burst noise
    burst_noise = _RNG.standard_normal(burst_n).astype(np.float32)
    aspiration  = _RNG.standard_normal(burst_n).astype(np.float32) * 0.15

    burst_bands = {
        "p":(800,3500,0.18), "b":(600,2500,0.13),
        "t":(2500,8000,0.22),"d":(1800,6000,0.16),
        "k":(1500,6000,0.20),"g":(1200,4500,0.14),
    }
    lo, hi, amp = burst_bands.get(ph, (1000,5000,0.16))
    burst = bpf(burst_noise, lo, hi, order=2)

    # Aspiration after voiceless stops (VOT)
    if ph in {"p","t","k"}:
        asp = lpf(aspiration, 4000, 2)
        asp_env = np.linspace(0,1,burst_n,dtype=np.float32) * np.linspace(1,0.3,burst_n,dtype=np.float32)
        burst = burst + 0.4*asp*asp_env

    # Envelope: sharp attack, decay
    burst_env = np.zeros(burst_n, dtype=np.float32)
    atk = max(1, int(burst_n*0.08))
    burst_env[:atk] = _ramp(atk)
    burst_env[atk:] = np.linspace(1, 0.05, burst_n-atk, dtype=np.float32)
    burst = amp * burst * burst_env

    out = np.concatenate([np.zeros(closure, dtype=np.float32), burst])

    # Voiced: voicing bar during closure
    if ph in {"b","d","g"} and voiced_f0 is not None:
        vn = min(closure, len(voiced_f0))
        vo = glottal_source(voiced_f0[:vn], 0.0)
        vo = lpf(vo, 500, 2)
        vo_env = np.linspace(0.0, 0.3, vn, dtype=np.float32)
        out[:vn] += vo * vo_env

    return out[:n]

def synth_nasal(ph: str, n: int, f0: np.ndarray) -> np.ndarray:
    src = glottal_source(f0, 0.06)
    # Nasal resonances — low F1 + anti-formants → use cascade LP here
    if ph == "m":
        out = lpf(src, 350, 4)
    elif ph == "n":
        out = bpf(src, 200, 500, 3)
        out += 0.3 * bpf(src, 1500, 2000, 2)
    else:  # ng
        out = bpf(src, 200, 450, 3)
        out += 0.25 * bpf(src, 2000, 2500, 2)

    out *= 0.65
    rel = max(1, int(n*0.15))
    env = np.ones(n, dtype=np.float32)
    env[-rel:] = _ramp(rel)[::-1]
    return (out * env).astype(np.float32)

def synth_approximant(ph: str, n: int, f0: np.ndarray,
                      f_prev=None, f_next=None) -> np.ndarray:
    src = glottal_source(f0, 0.08)
    loci = CONSONANT_LOCUS[ph]
    # Use formant targets for approximant (they're vowel-like)
    fmts = [(loci[0],80), (loci[1],120), (loci[2],180), (loci[3],200)]
    out = parallel_formant_synth(src, fmts, [0,-4,-8,-16])

    # Smooth transitions
    trans = max(1, int(n*0.4))
    if f_prev:
        for ch in range(4):
            pass  # formant already at locus
    if f_next:
        pass

    env = np.ones(n, dtype=np.float32)
    rel = max(1, int(n*0.15))
    env[-rel:] = _ramp(rel)[::-1]
    out *= 0.70 * env
    return out.astype(np.float32)

def synth_affricate(ph: str, n: int, f0: np.ndarray) -> np.ndarray:
    stop_n = max(1, int(n * 0.40))
    fric_n = n - stop_n
    base = "t" if ph == "ch" else "d"
    fric = "sh" if ph == "ch" else "zh"
    f0_v = f0 if ph == "j" else None
    s = synth_stop(base, stop_n, f0_v)
    f = synth_fricative(fric, fric_n, f0_v if ph=="j" else None)
    return np.concatenate([s, f]).astype(np.float32)

def synth_h(n: int, f_next=None) -> np.ndarray:
    """Aspirate /h/ shaped by upcoming vowel"""
    noise = _RNG.standard_normal(n).astype(np.float32)
    noise = lpf(noise, 4000, 2)
    if f_next:
        # colour noise with next-vowel formants
        fmts = [(f_next[0],120),(f_next[1],150),(f_next[2],200)]
        noise = parallel_formant_synth(noise, fmts, [0,-5,-10])
    else:
        noise = bpf(noise, 500, 4500, 2)
    atk = max(1,int(n*0.15)); rel = max(1,int(n*0.25))
    env = np.ones(n,dtype=np.float32)
    env[:atk] = _ramp(atk); env[-rel:] = _ramp(rel)[::-1]
    return (0.30 * noise * env).astype(np.float32)

# ────────────────────────────────────────────────────────────────────────────
# Assembler with coarticulation context
# ────────────────────────────────────────────────────────────────────────────

def _context_formants(ph: str) -> Optional[Tuple]:
    if ph in ALL_VOWELS:       return VOWEL_F[ph]
    if ph in CONSONANT_LOCUS:  return CONSONANT_LOCUS[ph]
    return None

def synthesize_text(text: str, speed: float = 1.0) -> np.ndarray:
    seq = text_to_phones(text)  # [(ph, stressed, final), ...]
    if not seq: return np.zeros(SR//10, dtype=np.float32)

    # Count only voiced+consonant tokens for phrase position
    voiced_total = max(1, sum(1 for p,_,_ in seq if p not in (PAUSE_LONG,PAUSE_SHORT,PAUSE_WORD)))
    voiced_count = 0

    segments: List[np.ndarray] = []

    for idx, (ph, stressed, final) in enumerate(seq):
        # Pauses
        if ph == PAUSE_LONG:
            segments.append(np.zeros(int(0.32*SR), dtype=np.float32)); continue
        if ph == PAUSE_SHORT:
            segments.append(np.zeros(int(0.13*SR), dtype=np.float32)); continue
        if ph == PAUSE_WORD:
            segments.append(np.zeros(int(0.045*SR), dtype=np.float32)); continue

        n = phoneme_dur(ph, stressed, speed)
        phrase_pos = voiced_count / voiced_total
        f0 = f0_contour(n, stressed, phrase_pos)

        # Coarticulation context
        prev_ph = seq[idx-1][0] if idx > 0 else None
        next_ph = seq[idx+1][0] if idx < len(seq)-1 else None
        f_prev = _context_formants(prev_ph) if prev_ph else None
        f_next = _context_formants(next_ph) if next_ph else None

        if ph in ALL_VOWELS:
            seg = synth_vowel(ph, n, f0, f_prev, f_next)
        elif ph in {"m","n","ng"}:
            seg = synth_nasal(ph, n, f0)
        elif ph in {"l","r","w","y"}:
            seg = synth_approximant(ph, n, f0, f_prev, f_next)
        elif ph == "h":
            seg = synth_h(n, f_next if next_ph and next_ph in ALL_VOWELS else None)
        elif ph in {"s","z","sh","zh","f","v","th","dh"}:
            seg = synth_fricative(ph, n, f0 if ph in {"v","z","zh","dh"} else None)
        elif ph in {"p","b","t","d","k","g"}:
            seg = synth_stop(ph, n, f0 if ph in {"b","d","g"} else None)
        elif ph in {"ch","j"}:
            seg = synth_affricate(ph, n, f0)
        else:
            seg = np.zeros(n, dtype=np.float32)

        # Pad/trim to exact n
        if len(seg) < n: seg = np.pad(seg,(0,n-len(seg)))
        seg = seg[:n].astype(np.float32)
        segments.append(seg)
        voiced_count += 1

    audio = np.concatenate(segments).astype(np.float32)

    # ── Post-processing ──────────────────────────────────────────────────
    # 1. De-emphasis (undo lip radiation pre-emphasis artifact)
    audio = lfilter([1.0], [1.0, -0.97], audio).astype(np.float32)

    # 2. Gentle low-pass to remove aliasing / harshness
    audio = lpf(audio, 8000, 2)

    # 3. Presence boost (2-4 kHz) for intelligibility
    presence = bpf(audio, 2000, 4500, 2)
    audio = audio + 0.18 * presence

    # 4. Soft-knee limiter
    threshold = 0.72
    mask = np.abs(audio) > threshold
    audio[mask] = np.sign(audio[mask]) * (threshold + (1-threshold)*np.tanh(
        (np.abs(audio[mask]) - threshold) / (1-threshold)))

    # 5. Final normalize
    pk = np.max(np.abs(audio))
    if pk > 0: audio *= 0.90 / pk

    return audio


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────
def save_wav(path: str, audio: np.ndarray) -> None:
    wavfile.write(path, SR, (np.clip(audio,-1,1)*32767).astype(np.int16))

def main():
    ap = argparse.ArgumentParser(description="High-quality pure-Python English TTS")
    ap.add_argument("--text",  required=True)
    ap.add_argument("--out",   default="out.wav")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="Speaking rate (0.7=slow … 1.5=fast)")
    args = ap.parse_args()
    print(f'Synthesizing: "{args.text}"')
    audio = synthesize_text(args.text, speed=args.speed)
    save_wav(args.out, audio)
    print(f"✓  {args.out}  ({len(audio)/SR:.2f}s)")

if __name__ == "__main__":
    main()