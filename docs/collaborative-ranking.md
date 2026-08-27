# Collaborative ranking calculation

Taste-twin evidence is derived only from persisted 384-dimensional user vectors and
positive reviews or explicit `like`, `save`, `order`, and `tried` interactions. Clicks
are excluded. A neighbour must pass both configured cosine-similarity and shared-evidence
thresholds. Evidence is recency-adjusted, each neighbour is capped at one contribution,
and at most five neighbours contribute to one dish.

The collaborative dish score is the mean of capped `neighbour_similarity × evidence_quality`
contributions, scaled to 0–100. It is incorporated inside food/profile compatibility as:

`food_profile = 70% content-profile score + 30% collaborative score`

Missing content evidence uses the existing neutral score. Missing collaborative evidence
leaves the original content score unchanged. The authoritative top-level weights remain
45% taste, 20% food/profile, 10% reviews, 10% distance, 10% price, and 5% popularity.
