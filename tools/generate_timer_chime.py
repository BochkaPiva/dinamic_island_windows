# SPDX-License-Identifier: GPL-3.0-only
"""Recreate our original synthesized timer chime; no sampled or recorded audio."""
from pathlib import Path
import math
import struct
import wave

rate=24000
samples=[]
for n in range(int(rate*3.0)):
    t=n/rate
    value=0.
    for start,frequency in ((0.,659.255),(.19,830.609),(.38,987.767)):
        elapsed=t-start
        if 0<=elapsed<1.25:
            envelope=(1-math.exp(-elapsed*95))*math.exp(-elapsed*5.8)
            value+=.20*envelope*(math.sin(2*math.pi*frequency*elapsed)+.13*math.sin(2*math.pi*2*frequency*elapsed))
    samples.append(struct.pack('<h',round(max(-.8,min(.8,value))*32767)))
target=Path(__file__).resolve().parents[1]/"island/assets/timer-chime.wav"
with wave.open(str(target),'wb') as output:
    output.setparams((1,2,rate,0,'NONE','not compressed'))
    output.writeframes(b''.join(samples))
