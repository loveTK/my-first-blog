\version "2.22.0"
\include "_common.ily"
\score { \new PianoStaff <<
  \new Staff { \clef treble \key g \major \time 3/4 \partial 4 d'4 |
    g'4 g'8 a' g' fis' | e'4 e' e' | a'4 a'8 b' a' g' | fis'4 d' d' |
    b'4 b'8 c'' b' a' | g'4 e' d'8 d' | e'4 a' fis' | g'2 d'4 |
    g'2 g'4 | fis'2 fis'4 | g'4 fis' e' | d'2 a'4 |
    b'4 a' g' | d''4 d'' d''8 d'' | e''4 a' fis' | g'2 \bar "|." }
  \new Staff { \clef bass \key g \major \time 3/4 \partial 4 r4 |
    <g, b, d>2. | <c e g> | <d fis a> | <g, b, d> |
    <e g b> | <c e g> | <d fis a> | <g, b, d>2 r4 |
    <g, b, d>2. | <d fis a> | <c e g> | <d fis a> |
    <g, b, d> | <g, b, d> | <d fis a> | <g, b, d>2 \bar "|." } >> \layout { } }
