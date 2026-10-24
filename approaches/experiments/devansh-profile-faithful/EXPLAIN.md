# In plain words

Before choosing any rules, Claude studies the product the way an engineer would: it reads the description AND the
exploded-view drawing. The drawing's labels are targets ("stop lamp 60 to 185 cd", "no water after the spray test",
"visible to 45 degrees outboard") that point straight at specific regulation paragraphs, and the drawing shows things
the text leaves implicit (several lamps in one housing, LED modules on a circuit board). Claude writes this down as a
product profile, and every later step works from it. The rule search also looks at rules written without the word
"shall" (like "In height: not less than 250 mm"), which the experts list too. Then the faithful writer and the 1-5
final check, as in our best version.

# Technical

1. `profile.build_profile`: `claude-opus-5-5` (effort high) with spec.md + exploded_view.png -> functions, components,
   configuration, performance callouts, features present / not stated, expected requirement topics; rendered as a
   "Product profile" section appended to the spec (`outputs/spec-with-profile-<case>.md`). Not-stated features are
   framed so conditional rules are KEPT with their condition (experts list them that way).
2. Regulation selection `combined` (rules + supersession + category filters).
3. Candidates `shall+implicit`: shall / must clauses plus clauses matching an implicit-obligation pattern (comparisons
   like "not less than", "is not permitted", "provided that", test instructions, "Label: value" lines, values with units).
   Dev: 1,599 candidates reach 108 of 121 expert paragraphs (shall only: 1,240 / 98).
4. Clause classifier (opus 5.5, effort medium) with the profile-augmented spec; faithful writer; `refine --mode rank
   --drop-at-or-below 1` with the augmented spec.
5. Scored with `bench.py` and `req_judge.py` on dev-rear-lamp and holdout-acpe (no image: profile from the spec only).
