\version "2.22.0"
\include "_common.ily"
\score { \new PianoStaff <<
  \new Staff { \clef treble \key g \major \time 3/4 \partial 4 d'4 |
    g'2 b'8 g' | b'2 a'4 | g'2 e'4 | d'2 d'4 |
    g'2 b'8 g' | b'2 a'4 | d''2. | b'2 d''8 b' |
    d''2 b'8 g' | b'2 a'4 | g'2 e'4 | d'2 d'4 |
    g'2 b'8 g' | b'2 a'4 | g'2. \bar "|." }
  \new Staff { \clef bass \key g \major \time 3/4 \partial 4 r4 |
    <g, b, d>2. | <g, b, d> | <c e g> | <d fis a> |
    <g, b, d> | <g, b, d> | <d fis a> | <d fis a> |
    <g, b, d> | <g, b, d> | <c e g> | <d fis a> |
    <g, b, d> | <d fis a> | <g, b, d>2. \bar "|." } >> \layout { } }
