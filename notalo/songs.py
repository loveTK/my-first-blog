"""곡 페이지 메타. 악보는 songs/<slug>.ly(내가 직접 입력한 퍼블릭 도메인 멜로디 + 단순 왼손), 산출물은 tools/build_songs.py가
static/songs/<slug>.{png,mid,json}으로 만듦. 저작권: 여기 있는 곡은 전부 작곡가 사후 70년 지난 PD. 가사는 안 씀. 편곡은 우리 것."""

SONGS = {
    "jingle-bells": {
        "title": "Jingle Bells", "composer": "James Lord Pierpont", "year": 1857, "key": "G major", "time": "4/4", "bpm": 120,
        "christmas": True,
        "intro": "The chorus everyone knows, then the first verse (“Dashing through the snow”), in G major with one sharp: every F is F♯. The right hand stays inside one octave, so it is a good first Christmas piece.",
        "tips": ["Chorus first: bars 1–8 are just B, D, G, A and C — five notes.", "The left hand is one chord per bar; hold it and let the melody do the work.", "Watch the F♯ in the verse (bar 22): it is the only sharp in the whole piece."],
    },
    "silent-night": {
        "title": "Silent Night", "composer": "Franz Xaver Gruber", "year": 1818, "key": "C major", "time": "6/8", "bpm": 60,
        "christmas": True,
        "intro": "Gruber’s carol in C major, so there are no sharps or flats at all. The 6/8 time means two gentle pulses per bar — count “1-2-3 4-5-6” and let the dotted rhythm (long–short) rock the melody.",
        "tips": ["The opening G–A–G–E shape comes back four times; learn it once.", "Bar 9 has the highest note (F) and bar 12 ends on a long C.", "Play the left-hand chords softly — this one is about the melody."],
    },
    "we-wish-you-a-merry-christmas": {
        "title": "We Wish You a Merry Christmas", "composer": "Traditional (West Country, England)", "year": 1500, "year_text": "16th century", "key": "G major", "time": "3/4", "bpm": 132,
        "christmas": True,
        "intro": "The English carol in G major, 3/4 time. It starts on a pick-up note (a single D before the first full bar), and the same four-bar phrase is sung three times before “and a happy new year”.",
        "tips": ["Bars 1–4 and 5–8 are the same pattern one note higher each time — G, then A, then B.", "“Good tidings we bring” (bar 9) is the only place the tune sits still: long G, long F♯.", "The pick-up D at the very start is not a mistake; the first bar has only one beat."],
    },
    "deck-the-halls": {
        "title": "Deck the Halls", "composer": "Traditional (Welsh melody “Nos Galan”)", "year": 1500, "year_text": "16th century", "key": "C major", "time": "4/4", "bpm": 120,
        "christmas": True,
        "intro": "The Welsh melody in C major with no sharps or flats. Every “fa-la-la-la-la” is the same descending run, so once you have bar 1 you have most of the piece.",
        "tips": ["The first phrase steps straight down: G–F–E–D–C.", "Lines 1, 2 and 4 are nearly identical; only line 3 (bars 9–12) is new.", "Bar 11 has the one F♯ in the piece, then it returns to C major."],
    },
    "happy-birthday": {
        "title": "Happy Birthday", "composer": "Mildred J. Hill and Patty S. Hill (\u201cGood Morning to All\u201d)", "year": 1893, "key": "F major", "time": "3/4", "bpm": 100,
        "intro": "The melody every beginner is asked to play, in F major (one flat: every B is B\u266d). It starts with two quick pick-up notes on C, and the whole tune fits in eight bars.",
        "tips": ["The two C\u2019s before the first bar line are the \u201cHap-py\u201d pick-up \u2014 short and light.", "Bar 5 jumps up to the high C; that is the one stretch in the piece.", "Bar 6 has the B\u266d \u2014 the key signature applies it automatically."],
    },
    "fur-elise": {
        "title": "F\u00fcr Elise", "composer": "Ludwig van Beethoven", "year": 1810, "key": "A minor", "time": "3/8", "bpm": 72,
        "intro": "The famous opening eight bars, in A minor. Where Beethoven wrote a rest after the first note of a bar, this beginner arrangement holds the note instead, so the letters and the MIDI line up beat for beat.",
        "tips": ["The E\u2013D\u266f\u2013E\u2013D\u266f\u2013E trill is two keys next to each other: white E, black D\u266f.", "Bar 3 has G\u266f in the right hand and in the left-hand chord \u2014 both black keys.", "Play the left-hand chords as gently as you can; the melody is the whole point."],
    },
    "twinkle-twinkle-little-star": {
        "title": "Twinkle Twinkle Little Star", "composer": "Traditional (French, \u201cAh! vous dirai-je, maman\u201d)", "year": 1761, "year_text": "18th century", "key": "C major", "time": "4/4", "bpm": 100,
        "intro": "All white keys, C major, twelve bars. The first and last four bars are identical, and the middle four are one phrase played twice \u2014 so you only learn two ideas.",
        "tips": ["The opening C\u2013C\u2013G\u2013G jump is the only leap; everything else moves by step.", "Bars 5\u20138 (\u201cup above the world so high\u201d) walk straight down from G to D, twice.", "Two chords in the left hand per bar \u2014 C, F and G only."],
    },
    "canon-in-d": {
        "title": "Canon in D", "composer": "Johann Pachelbel", "year": 1680, "year_text": "c. 1680", "key": "D major", "time": "4/4", "bpm": 66,
        "intro": "The first violin entry of Pachelbel\u2019s Canon over the famous eight-note ground bass, simplified for one player. D major has two sharps: every F and every C are sharp.",
        "tips": ["The left hand plays the same eight bass notes forever: D A B F\u266f G D G A. Learn it first, with eyes closed.", "The right hand mostly steps down; the only tricky bar is 7 (D B D A).", "Keep it slow \u2014 66 BPM \u2014 and let the bass line lead."],
    },
    "ode-to-joy": {
        "title": "Ode to Joy", "composer": "Ludwig van Beethoven (Symphony No. 9)", "year": 1824, "key": "C major", "time": "4/4", "bpm": 108,
        "intro": "The theme from the Ninth Symphony, moved to C major so there are no sharps or flats. Sixteen bars; the third line (bars 9\u201312) is the only part that differs from the first.",
        "tips": ["The right hand uses only five notes for the first eight bars: C D E F G.", "Bar 4 and bar 8 end with a dotted quarter + eighth \u2014 \u201clong\u2013short\u201d.", "Bar 12 dips to the G below middle C, the lowest note in the piece."],
    },
    "amazing-grace": {
        "title": "Amazing Grace", "composer": "Traditional (\u201cNew Britain\u201d, Southern Harmony)", "year": 1835, "key": "G major", "time": "3/4", "bpm": 80,
        "intro": "The hymn tune in G major, 3/4 time, starting on a single pick-up note. It uses only the five notes of the pentatonic scale \u2014 G A B D E \u2014 so there are no half-steps to catch you out.",
        "tips": ["No F\u266f is ever played in the right hand, even though the key has one.", "Bars 7\u20138 reach the high D \u2014 the top of the tune.", "Hold the long notes for their full two beats; the tune is about breathing."],
    },
    "moonlight-sonata": {
        "title": "Moonlight Sonata (1st movement, easy)", "composer": "Ludwig van Beethoven", "year": 1801, "key": "A minor", "time": "12/8", "bpm": 50,
        "intro": "The opening eight bars of the first movement, moved from C\u266f minor to A minor and written in 12/8 so the triplets become plain eighth notes. Same shape, far fewer sharps.",
        "tips": ["Each bar is the same three-note pattern (low, middle, high) four times \u2014 learn one, get the bar.", "Bar 4 introduces G\u266f, a black key; it comes back in bar 7.", "Left hand holds long two-note chords; keep them quiet under the arpeggios."],
    },
    "minuet-in-g": {
        "title": "Minuet in G", "composer": "Christian Petzold (from the Notebook for Anna Magdalena Bach)", "year": 1725, "year_text": "c. 1725", "key": "G major", "time": "3/4", "bpm": 112,
        "intro": "The minuet everyone learns from the Anna Magdalena Bach notebook, first half (16 bars). G major, one sharp. The second eight bars repeat the first with a different ending.",
        "tips": ["Bar 3 climbs to the high G \u2014 the peak of the phrase.", "Bars 7\u20138 and 15\u201316 are the two endings: first to A, then home to G.", "Count \u201c1 2 3\u201d out loud; the quarter-then-eighths rhythm is the whole character."],
    },
    "greensleeves": {
        "title": "Greensleeves", "composer": "Traditional (English)", "year": 1580, "year_text": "16th century", "key": "A minor", "time": "6/8", "bpm": 92,
        "intro": "Verse and chorus in A minor, 6/8 time. The G\u266f and F\u266f accidentals give it the old modal color \u2014 watch for them, they are written in the bars where they happen.",
        "tips": ["The verse (bars 1\u201310) and chorus (bars 11\u201320) share the same second half.", "G\u266f appears in bars 4, 5, 9, 14, 15 and 19 \u2014 always a black key.", "6/8: two big beats per bar, three eighths each. Sway, don\u2019t march."],
    },
}
