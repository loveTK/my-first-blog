\version "2.22.0"
\include "_common.ily"
\score { \new PianoStaff <<
  \new Staff { \clef treble \key c \major \time 4/4
    c'4 c' g' g' | a' a' g'2 | f'4 f' e' e' | d' d' c'2 |
    g'4 g' f' f' | e' e' d'2 | g'4 g' f' f' | e' e' d'2 |
    c'4 c' g' g' | a' a' g'2 | f'4 f' e' e' | d' d' c'2 \bar "|." }
  \new Staff { \clef bass \key c \major \time 4/4
    <c e g>1 | <f, a, c>2 <c e g> | <f, a, c>2 <c e g> | <g, b, d>2 <c e g> |
    <c e g>2 <f, a, c> | <c e g>2 <g, b, d> | <c e g>2 <f, a, c> | <c e g>2 <g, b, d> |
    <c e g>1 | <f, a, c>2 <c e g> | <f, a, c>2 <c e g> | <g, b, d>2 <c e g> \bar "|." } >> \layout { } }
