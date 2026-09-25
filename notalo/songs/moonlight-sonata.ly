\version "2.22.0"
\include "_common.ily"
% 1악장 도입 8마디를 A단조·12/8로 옮긴 초보 편곡(원곡 C#단조·셋잇단). 셋잇단은 인식 안 되므로 12/8 8분음표로 씀.
\score { \new PianoStaff <<
  \new Staff { \clef treble \key a \minor \time 12/8
    e'8 a' c'' e' a' c'' e' a' c'' e' a' c'' | e'8 a' c'' e' a' c'' e' a' c'' e' a' c'' |
    c'8 f' a' c' f' a' c' f' a' c' f' a' | b8 e' gis' b e' gis' b e' gis' b e' gis' |
    e'8 a' c'' e' a' c'' e' a' c'' e' a' c'' | e'8 a' c'' e' a' c'' e' a' c'' e' a' c'' |
    c'8 f' a' c' f' a' b e' gis' b e' gis' | a'1. \bar "|." }
  \new Staff { \clef bass \key a \minor \time 12/8
    <a, e>2. <a, e>2. | <g, e>2. <g, e>2. | <f, c>2. <f, c>2. | <e, b,>2. <e, b,>2. |
    <a, e>2. <a, e>2. | <g, e>2. <g, e>2. | <f, c>2. <e, b,>2. | <a, e a>1. \bar "|." } >> \layout { } }
