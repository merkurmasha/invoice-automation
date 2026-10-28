# Bundled font: DejaVu Sans

`DejaVuSans.ttf` and `DejaVuSans-Bold.ttf` are from the official DejaVu
Fonts project release `version_2_37`:
https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37

They're free/open (Bitstream Vera-derived) and bundled here so the
synthetic-invoice generator (`src/synthetic/pdf_render.py`) can render
Catalan text with full accented-character and middle-dot (l·l) support,
regardless of which base14 PDF font reportlab would otherwise fall back
to. See `DEJAVU-LICENSE.txt` for the license text.
