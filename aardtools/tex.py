"""
This code is based on eqhtml module from `mt-math`_

.. _mt-math: http://www.amk.ca/python/code/mt-math

"""
from __future__ import with_statement
import os
import tempfile
import binascii
from glob import glob

tex_preamble = r'''
\documentclass{article}
\usepackage{amsmath}
\usepackage{amsthm}
\usepackage{amssymb}
\usepackage{bm}
\pagestyle{empty}
\begin{document}
'''

def toimg(equation):

    workdir = tempfile.mkdtemp(prefix='math-')
    tex_file = os.path.join(workdir, 'eq.tex')

    with open(tex_file, 'w+') as f: 
        f.write(tex_preamble)
        f.write("$%s$\n" % equation)
        f.write('\end{document}')

    latex_cmd = ('latex -halt-on-error -output-directory %s %s > /dev/null 2>&1' 
                 % (workdir, tex_file))

    sts = os.system(latex_cmd)
    if sts != 0:
        raise Exception("Couldn't convert equation '%s' (failed cmd: '%s')"
                        % (equation, latex_cmd))

    dvi_file = os.path.join(workdir, 'eq.dvi')
    png_file = os.path.join(workdir, 'eq.png')

    png_cmd = ('dvipng -T tight -x 1200 -z 9 -bg Transparent -o %s %s > /dev/null 2>&1' 
               % (png_file, dvi_file))
    sts = os.system(png_cmd)
    if sts != 0:
        raise Exception("Couldn't convert equation '%s' (failed cmd: '%s')"
                        % (equation, png_cmd))

    with open(png_file, 'rb') as png:
        png_data = png.read()

    imgdata = binascii.b2a_base64(png_data).replace('\n', '')

    for name in glob('%s/*'%workdir):
        os.remove(name)
    os.removedirs(workdir)

    return imgdata

