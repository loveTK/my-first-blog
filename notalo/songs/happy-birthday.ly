\version "2.22.0"
\include "_common.ily"
\score { \new PianoStaff <<
  \new Staff { \clef treble \key f \major \time 3/4 \partial 4 c'8. c'16 |
    d'4 c' f' | e'2 c'8. c'16 | d'4 c' g' | f'2 c'8. c'16 |
    c''4 a' f' | e'4 d' bes'8. bes'16 | a'4 f' g' | f'2. \bar "|." }
  \new Staff { \clef bass \key f \major \time 3/4 \partial 4 r4 |
    <f, a, c>2. | <c e g> | <c e g> | <f, a, c> |
    <f, a, c> | <bes, d f> | <f, a, c>2 <c e g>4 | <f, a, c>2. \bar "|." } >> \layout { } }
