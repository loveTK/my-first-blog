\version "2.22.0"
\include "_common.ily"
\score { \new PianoStaff <<
  \new Staff { \clef treble \key g \major \time 3/4
    d''4 g'8 a' b' c'' | d''4 g' g' | e''4 c''8 d'' e'' fis'' | g''4 g' g' |
    c''4 d''8 c'' b' a' | b'4 c''8 b' a' g' | fis'4 g'8 a' b' g' | a'2. |
    d''4 g'8 a' b' c'' | d''4 g' g' | e''4 c''8 d'' e'' fis'' | g''4 g' g' |
    c''4 d''8 c'' b' a' | b'4 c''8 b' a' g' | a'4 b'8 a' g' fis' | g'2. \bar "|." }
  \new Staff { \clef bass \key g \major \time 3/4
    <g, b, d>2. | <g, b, d> | <c e g> | <g, b, d> |
    <c e g> | <g, b, d> | <d fis a> | <d fis a> |
    <g, b, d> | <g, b, d> | <c e g> | <g, b, d> |
    <c e g> | <g, b, d> | <d fis a> | <g, b, d> \bar "|." } >> \layout { } }
