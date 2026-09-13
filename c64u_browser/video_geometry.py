# SPDX-License-Identifier: GPL-3.0-or-later
"""Native-pixel aspect geometry, independent of GTK and stream ownership."""
def fit(width, height, available_width, available_height, integer=False):
    if min(width,height,available_width,available_height) <= 0:return (0,0,0,0)
    scale=min(available_width/width,available_height/height)
    if integer and scale>=1:scale=max(1,int(scale))
    w=max(1,int(width*scale));h=max(1,int(height*scale))
    return ((available_width-w)//2,(available_height-h)//2,w,h)
