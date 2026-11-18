import re

def lines(text):
    return re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)",text)[:-1] if text else []
