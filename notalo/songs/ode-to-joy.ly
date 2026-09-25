\version "2.22.0"
\include "_common.ily"
\score { \new PianoStaff <<
  \new Staff { \clef treble \key c \major \time 4/4
    e'4 e' f' g' | g' f' e' d' | c' c' d' e' | e'4. d'8 d'2 |
    e'4 e' f' g' | g' f' e' d' | c' c' d' e' | d'4. c'8 c'2 |
    d'4 d' e' c' | d' e'8 f' e'4 c' | d' e'8 f' e'4 d' | c' d' g2 |
    e'4 e' f' g' | g' f' e' d' | c' c' d' e' | d'4. c'8 c'2 \bar "|." }
  \new Staff { \clef bass \key c \major \time 4/4
    <c e g>1 | <c e g>2 <g, b, d> | <c e g>1 | <g, b, d>2 <c e g> |
    <c e g>1 | <c e g>2 <g, b, d> | <c e g>1 | <g, b, d>2 <c e g> |
    <g, b, d>2 <c e g> | <c e g>1 | <c e g>2 <g, b, d> | <c e g>2 <g, b, d> |
    <c e g>1 | <c e g>2 <g, b, d> | <c e g>1 | <g, b, d>2 <c e g> \bar "|." } >> \layout { } }
