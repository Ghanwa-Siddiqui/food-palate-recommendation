from collections import Counter

from app.services.ranking.scoring import calculate_cosine_similarity
from scripts.seed_customer_taste_demo import CLUSTERS as WAVE1_CLUSTERS
from scripts.seed_customer_taste_demo import plan as wave1_plan
from scripts.seed_customer_taste_demo_wave2 import (
    BATCH,
    CLUSTERS,
    MEMBERS_PER_CLUSTER,
    plan,
)


def test_wave2_plan_counts_clusters_vectors_and_feedback():
    users, feedback = plan()
    expected_users = len(CLUSTERS) * MEMBERS_PER_CLUSTER
    assert BATCH == "customer-taste-demo-wave2-v1"
    assert len(users) == expected_users
    assert len(feedback) == expected_users * 4
    assert {
        sum(user["cluster"] == cluster[0] for user in users) for cluster in CLUSTERS
    } == {MEMBERS_PER_CLUSTER}
    assert all(len(user["vector"]) == 384 for user in users)
    assert {
        sum(row["user_index"] == index for row in feedback) for index in range(expected_users)
    } == {4}
    assert all(
        len({row["dish_id"] for row in feedback if row["user_index"] == index}) == 4
        for index in range(expected_users)
    )
    # Emails and names must not collide with wave 1's fixed 30-user batch.
    assert all(user["email"].startswith("customer.taste.demo.wave2.") for user in users)
    assert len({user["email"] for user in users}) == expected_users
    assert len({user["name"] for user in users}) == expected_users

    ratings = Counter(row["rating"] for row in feedback)
    assert {1, 2} & set(ratings) and {4, 5} & set(ratings)

    for cluster_index, cluster in enumerate(CLUSTERS):
        start = cluster_index * MEMBERS_PER_CLUSTER
        members = users[start : start + MEMBERS_PER_CLUSTER]
        assert cluster[0] == members[0]["cluster"]
        assert (
            min(
                calculate_cosine_similarity(members[0]["vector"], member["vector"])
                for member in members[1:]
            )
            >= 0.65
        )
        rows = [
            row
            for row in feedback
            if start <= row["user_index"] < start + MEMBERS_PER_CLUSTER
        ]
        positives = Counter(row["dish_id"] for row in rows if row["rating"] >= 4)
        assert sum(count >= 2 for count in positives.values()) >= 2


def test_wave2_members_are_taste_similar_to_wave1_members_in_the_same_archetype():
    """The concrete proof "more users" helps everyone: a wave-2 member's vector
    is cosine-similar to at least one already-seeded wave-1 member in the same
    cluster archetype, at the same 0.65 threshold the real ranking service
    uses for collaborative evidence - so wave 1 users gain new taste twins
    too, without their own data ever being touched.
    """
    wave1_users, _ = wave1_plan()
    wave2_users, _ = plan()
    assert [c[0] for c in WAVE1_CLUSTERS] == [c[0] for c in CLUSTERS]

    by_cluster_wave1: dict[str, list[list[float]]] = {}
    for user in wave1_users:
        by_cluster_wave1.setdefault(user["cluster"], []).append(user["vector"])

    for cluster in CLUSTERS:
        label = cluster[0]
        wave1_vectors = by_cluster_wave1[label]
        start = [c[0] for c in CLUSTERS].index(label) * MEMBERS_PER_CLUSTER
        sample = wave2_users[start]
        best = max(
            calculate_cosine_similarity(sample["vector"], other) for other in wave1_vectors
        )
        assert best >= 0.65, f"no wave-1 taste twin found for wave-2 cluster {label!r}"
