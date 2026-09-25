\version "2.22.0"
\include "_common.ily"
\score { \new PianoStaff <<
  \new Staff { \clef treble \key a \minor \time 6/8 \partial 8 a'8 |
    c''4 d''8 e''4 f''8 | e''4 d''8 b'4 g'8 | a'4 b'8 c''4 a'8 | a'4 gis'8 a'4 b'8 |
    gis'4 e'8 e'4 a'8 | c''4 d''8 e''4 f''8 | e''4 d''8 b'4 g'8 | a'4 b'8 c''4 b'8 |
    a'4 gis'8 fis'4 gis'8 | a'4. a'4 g''8 | g''4. g''4 f''8 | e''4 d''8 b'4 g'8 |
    a'4 b'8 c''4 a'8 | a'4 gis'8 a'4 b'8 | gis'4 e'8 e'4 g''8 | g''4. g''4 f''8 |
    e''4 d''8 b'4 g'8 | a'4 b'8 c''4 b'8 | a'4 gis'8 fis'4 gis'8 | a'2. \bar "|." }
  \new Staff { \clef bass \key a \minor \time 6/8 \partial 8 r8 |
    <a, c e>2. | <g, b, d> | <f, a, c> | <e, gis, b,> |
    <e, gis, b,>4. <a, c e> | <a, c e>2. | <g, b, d> | <f, a, c> |
    <e, gis, b,> | <a, c e> | <c e g> | <g, b, d> |
    <f, a, c> | <e, gis, b,> | <e, gis, b,>4. <a, c e> | <c e g>2. |
    <g, b, d> | <f, a, c> | <e, gis, b,> | <a, c e>2. \bar "|." } >> \layout { } }
