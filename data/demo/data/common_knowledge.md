# Synthetic demo knowledge

All rows, identifiers, table names and questions in this profile were created for this open-source demo. They do not contain competition records.

- Dates are strings in `YYYYMMDD` format.
- `demo_sessions` stores player activity and duration; players may appear on multiple dates.
- `demo_player_tags` stores daily player segments. Match the requested snapshot date when joining.
- Count distinct players when computing retention. The denominator is the number of active players on the base date.
- Return ratios as decimals, rounded to two decimal places. Return actual SQL execution results, never fabricate rows.
