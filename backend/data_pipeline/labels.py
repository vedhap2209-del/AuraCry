"""ONE label set shared by the ML model, the DL model, fusion and the UI.

Why these 5: they are the only cry reasons with (a) curated recordings in Donate-a-Cry and (b) a 1:1 counterpart in the
Dunstan Baby Language scheme used by InfantCry-DBL, so every source can be mapped without guessing.
Dropped on purpose: lonely / scared (no curated recordings, no counterpart in any other source), don't-know (no label).
cold/hot is merged into discomfort, following the Donate-a-Cry curators (KTH cleaned corpus README).
"""
CLASSES = ["hungry", "tired", "discomfort", "belly_pain", "burping"]       # fixed order = probability vector order
DISPLAY = {"hungry": "Hungry", "tired": "Tired", "discomfort": "Discomfort", "belly_pain": "Belly Pain", "burping": "Needs Burping"}

# source label -> standard label (None = excluded, with the reason kept in the manifest)
DONATEACRY_TAG = {"hu": "hungry", "ti": "tired", "dc": "discomfort", "ch": "discomfort", "bp": "belly_pain", "bu": "burping",
                  "lo": None, "sc": None, "dk": None}
DONATEACRY_FOLDER = {"hungry": "hungry", "tired": "tired", "discomfort": "discomfort", "belly_pain": "belly_pain", "burping": "burping"}
# Dunstan Baby Language sounds (InfantCry-DBL folders). Neh=hungry, Owh=sleepy, Heh=discomfort, Eairh=lower gas, Eh=burp.
DUNSTAN = {"neh": "hungry", "owh": "tired", "heh": "discomfort", "eairh": "belly_pain", "eh": "burping"}
