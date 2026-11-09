# Design: Does the Sheep Remember the Wolf?

**Artifact:** public benchmark site, mixed: explorable hero, data dashboard, printable cards. Audience arrives from X and must grasp the test in 20 seconds.

**Words:** surveyed, plain-spoken, exact, a little rural.

**Aesthetic:** a printed land-survey sheet. Pale lichen paper, bottle-green ink, spot colours as a mapmaker would overprint them: survey magenta for the wolf and every warning, four flat field tints, contour ochre.

**Signature move:** each model is a surveyed parcel. Four boundary stones on north, east, south and west bearings, one per sub-score. The same shape appears in the leaderboard, on the model page and on the downloadable card. The sheet itself carries a neat line and graticule ticks.

## Tokens

All colour tokens live on `:root` in `src/styles.css` and canvas code reads them through `token()`, so CSS and canvas share one palette. Light only: the site is a printed object and the cards must match it.

- Type: Sofia Sans Extra Condensed (display, numerals), Sofia Sans (body), Old Standard TT italic (field names and the diary, as engraved names on a map). Self-hosted through Fontsource.
- Scale: 0.875, 1.0625, 1.3125, 1.75, 2.5rem, then a fluid display size. Ratio about 1.3.
- Spacing base 4px, tight inside groups, 48px between sections. Radius 3px on controls, none on map-derived frames.
- Chart series pass the dataviz validator on the surface colour. Green and ochre sit in the CVD warning band, so every chart has a legend, direct labels at wide widths, and a table view. Baselines are dashed ink.

## Craft decisions

- Field: Canvas 2D, seeded Voronoi fields, mown stripes, marching-squares contours, fence posts. Marks are crosses, stale marks hollow rings, memory views dim or remove them. Every canvas action has a button equivalent.
- Motion: only the field's playback. Under reduced motion it opens at the last day with no pings.
- Demo data shows a stamp on every page and across every card. The stamp crosses the flock score deliberately, so a mock number cannot be cropped into looking real.

## Slop audit

Checked against the frontend-design-deslop list on rendered screenshots at 1360px and 390px: no cream-and-serif, no acid accent, no card grid, no uppercase eyebrows except the required demo stamp. Horizontal overflow at phone width is 0px.
