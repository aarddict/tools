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
import xml.etree.ElementTree as etree

from subprocess import Popen, PIPE

latex_doc = r'''\documentclass{article}
\usepackage{amsmath}
\usepackage{amsthm}
\usepackage{amssymb}
\usepackage{bm}
\pagestyle{empty}

%% The following new command definitions and comments are copied
%% from Blahtex(ml) (http://gva.noekeon.org/blahtexml/)
%% for texvc compatibility

%% First we have some macros which are not part of tex/latex/amslatex
%% but which texvc recognises, so for backward compatibility we define
%% them here too. Most of these are apparently intended to cater for
%% those more familiar with HTML entities.

\newcommand{\R}{{\mathbb R}}
\newcommand{\Reals}{\R}
\newcommand{\reals}{\R}
\newcommand{\Z}{{\mathbb Z}}
\newcommand{\N}{{\mathbb N}}
\newcommand{\natnums}{\N}
\newcommand{\Complex}{{\mathbb C}}
\newcommand{\cnums}{\Complex}
\newcommand{\alefsym}{\aleph}
\newcommand{\alef}{\aleph}
\newcommand{\larr}{\leftarrow}
\newcommand{\rarr}{\rightarrow}
\newcommand{\Larr}{\Leftarrow}
\newcommand{\lArr}{\Leftarrow}
\newcommand{\Rarr}{\Rightarrow}
\newcommand{\rArr}{\Rightarrow}
\newcommand{\uarr}{\uparrow}
\newcommand{\uArr}{\Uparrow}
\newcommand{\Uarr}{\Uparrow}
\newcommand{\darr}{\downarrow}
\newcommand{\dArr}{\Downarrow}
\newcommand{\Darr}{\Downarrow}
\newcommand{\lrarr}{\leftrightarrow}
\newcommand{\harr}{\leftrightarrow}
\newcommand{\Lrarr}{\Leftrightarrow}
\newcommand{\Harr}{\Leftrightarrow}
\newcommand{\lrArr}{\Leftrightarrow}
%% The next one looks like a typo in the texvc source code:
\newcommand{\hAar}{\Leftrightarrow}
\newcommand{\sub}{\subset}
\newcommand{\supe}{\supseteq}
\newcommand{\sube}{\subseteq}
\newcommand{\infin}{\infty}
\newcommand{\lang}{\langle}
\newcommand{\rang}{\rangle}
\newcommand{\real}{\Re}
\newcommand{\image}{\Im}
\newcommand{\bull}{\bullet}
\newcommand{\weierp}{\wp}
\newcommand{\isin}{\in}
\newcommand{\plusmn}{\pm}
\newcommand{\Dagger}{\ddagger}
\newcommand{\exist}{\exists}
\newcommand{\sect}{\S}
\newcommand{\clubs}{\clubsuit}
\newcommand{\spades}{\spadesuit}
\newcommand{\hearts}{\heartsuit}
\newcommand{\diamonds}{\diamondsuit}
\newcommand{\sdot}{\cdot}
\newcommand{\ang}{\angle}
\newcommand{\thetasym}{\theta}
\newcommand{\Alpha}{A}
\newcommand{\Beta}{B}
\newcommand{\Epsilon}{E}
\newcommand{\Zeta}{Z}
\newcommand{\Eta}{H}
\newcommand{\Iota}{I}
\newcommand{\Kappa}{K}
\newcommand{\Mu}{M}
\newcommand{\Nu}{N}
\newcommand{\Rho}{P}
\newcommand{\Tau}{T}
\newcommand{\Chi}{X}
\newcommand{\arccot}{\operatorname{arccot}}
\newcommand{\arcsec}{\operatorname{arcsec}}
\newcommand{\arccsc}{\operatorname{arccsc}}
\newcommand{\sgn}{\operatorname{sgn}}

%% The commands in this next group are defined in tex/latex/amslatex,
%% but they don't get mapped to what texvc thinks (e.g. "\part" is used
%% in typesetting books to mean a unit somewhat larger than a chapter,
%% like "Part IV").
%%
%% We'll stick to the way texvc does it, especially since wikipedia has
%% quite a number of equations using them.
\renewcommand{\empty}{\emptyset}
\renewcommand{\and}{\wedge}
\renewcommand{\or}{\vee}
\renewcommand{\part}{\partial}

%% Now we come to the xxxReserved commands. These are all implemented
%% as macros in TeX, so for maximum compatibility, we want to treat
%% their arguments the way a TeX macro does. The strategy is the
%% following. First, in Manager::ProcessInput, we convert e.g. "\mbox"
%% into "\mboxReserved". Then, the MacroProcessor object sees e.g.
%% "\mboxReserved A" and converts it to "\mbox{A}". This simplifies
%% things enormously for the parser, since now it can treat "\mbox"
%% and "\hbox" in the same way. ("\hbox" requires braces around its
%% argument, even if it's just a single character.) This strategy also
%% keeps TeX happy when we send off the purified TeX, since TeX doesn't
%% care about the extra braces.

\newcommand{\mboxReserved}     [1]{\mbox{#1}}
\newcommand{\substackReserved} [1]{\substack{#1}}
\newcommand{\oversetReserved}  [2]{\overset{#1}{#2}}
\newcommand{\undersetReserved} [2]{\underset{#1}{#2}}

%% The following are all similar, but they get extra "safety braces"
%% placed around them. For example, "x^\frac yz" is legal, because it
%% becomes "x^{y \over z}".

\newcommand{\textReserved}     [1]{{\text{#1}}}
\newcommand{\textitReserved}   [1]{{\textit{#1}}}
\newcommand{\textrmReserved}   [1]{{\textrm{#1}}}
\newcommand{\textbfReserved}   [1]{{\textbf{#1}}}
\newcommand{\textsfReserved}   [1]{{\textsf{#1}}}
\newcommand{\textttReserved}   [1]{{\texttt{#1}}}
\newcommand{\emphReserved}     [1]{{\emph{#1}}}
\newcommand{\fracReserved}     [2]{{\frac{#1}{#2}}}
\newcommand{\mathrmReserved}   [1]{{\mathrm{#1}}}
\newcommand{\mathbfReserved}   [1]{{\mathbf{#1}}}
\newcommand{\mathbbReserved}   [1]{{\mathbb{#1}}}
\newcommand{\mathitReserved}   [1]{{\mathit{#1}}}
\newcommand{\mathcalReserved}  [1]{{\mathcal{#1}}}
\newcommand{\mathfrakReserved} [1]{{\mathfrak{#1}}}
\newcommand{\mathttReserved}   [1]{{\mathtt{#1}}}
\newcommand{\mathsfReserved}   [1]{{\mathsf{#1}}}
\newcommand{\bigReserved}      [1]{{\big#1}}
\newcommand{\biggReserved}     [1]{{\bigg#1}}
\newcommand{\BigReserved}      [1]{{\Big#1}}
\newcommand{\BiggReserved}     [1]{{\Bigg#1}}

\newcommand{\japReserved}     [1]{{\jap{#1}}}
\newcommand{\cyrReserved}     [1]{{\cyr{#1}}}

\begin{document}
%s
\end{document}
'''

emptylines = re.compile(r'[\r\n]{2,}')


class MathRenderingFailed(Exception):

    def __init__(self, equation, cmd, error):
        Exception.__init__(self, equation, cmd, error)
        self.equation = equation
        self.cmd = cmd
        self.error = error

    def __str__(self):
        return ("Couldn't convert equation %r (failed cmd: %r, error: %r)"
                % (self.equation, self.cmd, self.error))



def mkpng_texvc(workdir, equation):
    cmd = ['texvc', workdir, workdir, equation, "UTF-8", "72"]
    sub = Popen(cmd, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    (result, error) = sub.communicate()
    if sub.returncode != 0:
        raise MathRenderingFailed(equation, ' '.join(cmd), error)
    else:
        png_fn = os.path.join(workdir, result[1:33] + '.png')
        return png_fn

def mkpng_blahtex(workdir, equation):
    tex_cmd = ['blahtexml', '--texvc-compatible-commands', '--png',
               '--temp-directory', workdir, '--png-directory', workdir]
    sub = Popen(tex_cmd, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    result, error = sub.communicate(equation)
    if sub.returncode != 0:
        raise MathRenderingFailed(equation, ' '.join(tex_cmd), error)
    e = etree.fromstring(result)
    png_fn = e.findtext('png/md5')
    if not png_fn:
        error = e.findtext('error/message')
        raise MathRenderingFailed(equation, ' '.join(tex_cmd), error)
    return os.path.join(workdir, os.path.extsep.join((png_fn, 'png')))

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
        raise MathRenderingFailed(equation, ' '.join(tex_cmd), error)

    dvi_file = os.path.join(workdir, 'eq.dvi')
    png_file = os.path.join(workdir, 'eq.png')

    png_cmd = ['dvipng', '-T', 'tight', '-x', '1200', '-z', '9',
               '-bg', 'Transparent', '-o', png_file, dvi_file]

    sub = Popen(png_cmd, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    error = sub.communicate()[1]
    if sub.returncode != 0:
        raise MathRenderingFailed(equation, ' '.join(png_cmd), error)
    return png_file


def toimg(equation, cmd='latex', keeptemp=False):
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
        if not keeptemp:
            shutil.rmtree(workdir)


