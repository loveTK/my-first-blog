\version "2.22.0"
\include "_common.ily"
\score { \new PianoStaff <<
  \new Staff { \clef treble \key c \major \time 4/4
    g'4 f'8 e' d'4 c' | d'4 e' f' d' | e'8 f' g' f' e'4 d' | c'4 b8 c' d'4 c' |
    g'4 f'8 e' d'4 c' | d'4 e' f' d' | e'8 f' g' f' e'4 d' | c'4 b8 c' d'4 c' |
    d'4 e'8 f' g'4 d' | e'4 f'8 g' a'4 d' | e'8 fis' g' e' fis'4 g' | a'4 b' c''2 |
    g'4 f'8 e' d'4 c' | d'4 e' f' d' | e'8 f' g' f' e'4 d' | c'4 b8 c' d'4 c' \bar "|." }
  \new Staff { \clef bass \key c \major \time 4/4
    <c e g>1 | <g, b, d> | <c e g>2 <g, b, d> | <c e g>1 |
    <c e g>1 | <g, b, d> | <c e g>2 <g, b, d> | <c e g>1 |
    <g, b, d>1 | <c e g>2 <g, b, d> | <c e g>2 <g, b, d> | <d fis a>2 <g, b, d> |
    <c e g>1 | <g, b, d> | <c e g>2 <g, b, d> | <c e g>1 \bar "|." } >> \layout { } }
