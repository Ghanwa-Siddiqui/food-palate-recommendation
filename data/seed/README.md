# Development sample dataset

`backend/scripts/seed.py` deterministically creates 30 synthetic restaurants, three dishes per restaurant, and one deal per restaurant across Pakistani, Chinese, Italian, Turkish, fast food, and continental cuisines. BBQ is represented as a preparation style; the corresponding sample restaurants and dishes are classified as Pakistani cuisine. Names and addresses are deliberately marked as samples and are not claims about verified real businesses.

The seed operation uses stable UUIDs and skips existing rows, making repeat runs
idempotent. It requires an explicit development-data confirmation flag and accepts only
local SQLite or PostgreSQL on a loopback host; all remote targets are rejected.
Embeddings are omitted by default so no model is downloaded; use the optional embedding
flag only in a prepared local environment.

The remote-development exception is documented in the repository README. It requires all
independent authorization gates plus migration/table/emptiness preflight checks. Remote
mode never enables embeddings and never seeds users, reviews, or interactions.
