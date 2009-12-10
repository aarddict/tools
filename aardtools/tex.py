"""
This code is based on eqhtml module from `mt-math`_

.. _mt-math: http://www.amk.ca/python/code/mt-math

"""
from __future__ import with_statement
import os
import tempfile
import binascii
import re
import shutil
from subprocess import Popen, PIPE

latex_doc = r'''\documentclass{article}
\usepackage{amsmath}
\usepackage{amsthm}
\usepackage{amssymb}
\usepackage{bm}
\pagestyle{empty}
\begin{document}
%s
\end{document}
'''

emptylines = re.compile(r'[\r\n]{2,}')

def mkpng_texvc(workdir, equation):
    cmd = ['texvc', workdir, workdir, equation, "UTF-8", "72"]
    sub = Popen(cmd, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    (result, error) = sub.communicate()
    if sub.returncode != 0:
        raise Exception("Couldn't convert equation '%s' (failed cmd: '%s', error: %s)"
                        % (equation, ' '.join(cmd), error))
    else:
        png_fn = os.path.join(workdir, result[1:33] + '.png')
        return png_fn

def mkpng_latex(workdir, equation):
    tex_file = os.path.join(workdir, 'eq.tex')
    
    equation = emptylines.sub('\n', equation)
    eq_stripped = equation.strip().lower()
    if not (eq_stripped.startswith(r'\begin') or
            eq_stripped.startswith('$') or
            eq_stripped.startswith('\\[')):
        equation = '\\[%s\\]' % equation

    doc_text = latex_doc % equation
    with open(tex_file, 'w+') as f:
        f.write(doc_text)

    tex_cmd = ['latex', '-halt-on-error', '-output-directory', workdir, tex_file]
    sub = Popen(tex_cmd, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    error = sub.communicate()[1]
    if sub.returncode != 0:
        raise Exception("Couldn't convert equation '%s' (failed cmd: '%s', error: %s)"
                        % (equation, ' '.join(tex_cmd), error))

    dvi_file = os.path.join(workdir, 'eq.dvi')
    png_file = os.path.join(workdir, 'eq.png')

    png_cmd = ['dvipng', '-T', 'tight', '-x', '1200', '-z', '9', 
               '-bg', 'Transparent', '-o', png_file, dvi_file] 

    sub = Popen(png_cmd, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    error = sub.communicate()[1]
    if sub.returncode != 0:
        raise Exception("Couldn't convert equation '%s' (failed cmd: '%s', error: %s)"
                        % (equation, ' '.join(png_cmd), error))
    return png_file
    

def toimg(equation, cmd='texvc'):
    try:        
        workdir = tempfile.mkdtemp(prefix='math-')        
        
        if isinstance(equation, unicode):
            equation = equation.encode('utf8')

        png_file = globals()['mkpng_'+cmd](workdir, equation)

        with open(png_file, 'rb') as png:
            png_data = png.read()

        imgdata = binascii.b2a_base64(png_data).replace('\n', '')
        return imgdata
    finally:
        shutil.rmtree(workdir)
    

