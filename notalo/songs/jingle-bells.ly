\version "2.22.0"
\include "_common.ily"
% 절대음정(c' = 가운데 C). \relative는 옥타브가 흘러내려서 안 씀.
\score { \new PianoStaff <<
  \new Staff { \clef treble \key g \major \time 4/4
    b'4 b' b'2 | b'4 b' b'2 | b'4 d'' g'4. a'8 | b'1 |
    c''4 c'' c''4. c''8 | c''4 b' b' b'8 b' | b'4 a' a' b' | a'2 d'' |
    b'4 b' b'2 | b'4 b' b'2 | b'4 d'' g'4. a'8 | b'1 |
    c''4 c'' c''4. c''8 | c''4 b' b' b'8 b' | d''4 d'' c'' a' | g'1 |
    d'4 b' a' g' | d'2. d'8 d' | d'4 b' a' g' | e'1 |
    e'4 c'' b' a' | fis'1 | d''4 d'' c'' a' | b'1 |
    d'4 b' a' g' | d'2. d'8 d' | d'4 b' a' g' | e'1 |
    e'4 c'' b' a' | d''4 d'' d'' d'' | e'' d'' c'' a' | g'1 \bar "|." }
  \new Staff { \clef bass \key g \major \time 4/4
    <g, b, d>1 | <g, b, d> | <c e g>2 <g, b, d> | <g, b, d>1 |
    <c e g>1 | <g, b, d> | <d fis a>2 <g, b, d> | <d fis a>1 |
    <g, b, d>1 | <g, b, d> | <c e g>2 <g, b, d> | <g, b, d>1 |
    <c e g>1 | <g, b, d> | <d fis a>2 <d fis a> | <g, b, d>1 |
    <g, b, d>1 | <g, b, d> | <g, b, d> | <c e g> |
    <c e g>2 <g, b, d> | <d fis a>1 | <d fis a>2 <d fis a> | <g, b, d>1 |
    <g, b, d>1 | <g, b, d> | <g, b, d> | <c e g> |
    <c e g>2 <g, b, d> | <d fis a>1 | <d fis a>2 <d fis a> | <g, b, d>1 \bar "|." } >> \layout { } }
