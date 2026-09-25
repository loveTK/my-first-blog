\version "2.22.0"
\paper { #(set-paper-size "a4") indent = 0 }
\score {
  \new PianoStaff <<
    \new Staff { \clef treble \time 4/4
      c'1 | d'2 e'2 | f'4 g'4 a'4 b'4 | c''8 d''8 e''8 f''8 g''4 a''4 |
      b''4. c'''8 d''2 | c''16 d''16 e''16 f''16 g''8 a''8 b''4 c''4 |
      \autoBeamOff e''8 d''4 c''8 b'8 a'8 g'4 | \autoBeamOn a'2. b'4 |
      c''16 d''16 e''8 f''4 g''4. a''8 | \autoBeamOff c''16 d''16 e''8 f''4 g''2 | c''1 \bar "|."
    }
    \new Staff { \clef bass \time 4/4
      c2 g2 | c1 | <c e g>4 <c e g>4 <d f a>2 | e4 f4 g2 |
      c8 d8 e8 f8 g2 | a4 b4 c'2 | d'4. e'8 f'2 | g'1 |
      c4 d4 e4 f4 | g2 a2 | c'1 \bar "|."
    }
  >>
  \layout { }
}
