\version "2.22.0"
\header { tagline = ##f }
\paper { #(set-paper-size "a4") indent = 0 top-margin = 12 left-margin = 14 right-margin = 14
  % 시스템 사이를 넓게: Notalo가 아래엔 왼손 글자, 위엔 코드를 붙이므로 겹치지 않게
  system-system-spacing = #'((basic-distance . 30) (minimum-distance . 26) (padding . 8) (stretchability . 60)) }
\layout { \context { \PianoStaff \override StaffGrouper.staff-staff-spacing = #'((basic-distance . 14) (minimum-distance . 12) (padding . 3)) } }
