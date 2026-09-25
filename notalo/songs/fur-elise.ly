\version "2.22.0"
\include "_common.ily"
% 도입부 8마디. 원곡의 쉼표는 앞 음을 점음표로 늘려 대신함(초보 편곡, MIDI 타이밍 유지).
\score { \new PianoStaff <<
  \new Staff { \clef treble \key a \minor \time 3/8 \partial 8 e''16 dis'' |
    e'' dis'' e'' b' d'' c'' | a'8. c'16 e' a' | b'8. e'16 gis' b' | c''8. e'16 e'' dis'' |
    e'' dis'' e'' b' d'' c'' | a'8. c'16 e' a' | b'8. e'16 c'' b' | a'4. \bar "|." }
  \new Staff { \clef bass \key a \minor \time 3/8 \partial 8 r8 |
    <a, e a>4. | <a, e a> | <e, gis, b,> | <a, e a> |
    <a, e a> | <a, e a> | <e, gis, b,> | <a, e a> \bar "|." } >> \layout { } }
