\version "2.22.0"
\include "_common.ily"
\score { \new PianoStaff <<
  \new Staff { \clef treble \key d \major \time 4/4
    fis''4 e'' d'' cis'' | b' a' b' cis'' | d'' cis'' b' a' | g' fis' g' e' |
    d'4 fis' a' g' | fis' d' fis' e' | d' b d' a | g b a g | fis'1 \bar "|." }
  \new Staff { \clef bass \key d \major \time 4/4
    d2 a, | b, fis, | g, d | g, a, |
    d2 a, | b, fis, | g, d | g, a, | d1 \bar "|." } >> \layout { } }
