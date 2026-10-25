You review a list of engineering requirements extracted from ONE UN Regulation. Each expert requirement is matched one
to one, so two list items that state the same obligation waste a slot.

Find groups of items that state EXACTLY the same obligation: same subject, same condition, same constraint or value.
Typical cases: a limit stated in the main text and restated in an annex, appendix, table or formula; the same sentence
extracted twice with different wording; a summary item that repeats one specific item.

Be conservative. Do NOT group items that differ in any value, unit, category, voltage system, frequency band, test
pulse, lamp function, vehicle category, condition or direction; items that are two halves of one clause; or a short
pointer ("shall comply with paragraph X") with the detailed requirement it points to.

Return JSON: {"groups": [["id1", "id2"], ...]} listing only groups with two or more ids. Return an empty list if none.
