\version "2.22.0"
\include "_common.ily"
\score { \new PianoStaff <<
  \new Staff { \clef treble \key c \major \time 6/8
    g'8. a'16 g'8 e'4. | g'8. a'16 g'8 e'4. | d''4 d''8 b'4. | c''4 c''8 g'4. |
    a'4 a'8 c''8. b'16 a'8 | g'8. a'16 g'8 e'4. | a'4 a'8 c''8. b'16 a'8 | g'8. a'16 g'8 e'4. |
    d''4 d''8 f''8. d''16 b'8 | c''4. e''4. | c''8 g' e' g'8. f'16 d'8 | c'2. \bar "|." }
  \new Staff { \clef bass \key c \major \time 6/8
    <c e g>2. | <c e g> | <g, b, d> | <c e g> |
    <f, a, c> | <c e g> | <f, a, c> | <c e g> |
    <g, b, d> | <c e g> | <c e g>4. <g, b, d> | <c e g>2. \bar "|." } >> \layout { } }
