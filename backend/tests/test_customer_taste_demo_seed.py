from collections import Counter

from app.services.ranking.scoring import calculate_cosine_similarity
from scripts.seed_customer_taste_demo import BATCH, CLUSTERS, plan


def test_customer_demo_plan_exact_counts_clusters_vectors_and_feedback():
    users, feedback = plan()
    assert BATCH == "customer-taste-demo-v1"
    assert len(users) == 30
    assert len(feedback) == 120
    assert len(CLUSTERS) == 6
    assert {sum(user["cluster"] == cluster[0] for user in users) for cluster in CLUSTERS} == {5}
    assert all(len(user["vector"]) == 384 for user in users)
    assert {sum(row["user_index"] == index for row in feedback) for index in range(30)} == {4}
    assert sum(user["public"] for user in users) == 20
    assert all(
        len({row["dish_id"] for row in feedback if row["user_index"] == index}) == 4
        for index in range(30)
    )
    assert Counter(row["rating"] for row in feedback) == {5: 33, 4: 33, 3: 30, 1: 12, 2: 12}
    for cluster_index, cluster in enumerate(CLUSTERS):
        members = users[cluster_index * 5 : cluster_index * 5 + 5]
        assert (
            min(
                calculate_cosine_similarity(members[0]["vector"], member["vector"])
                for member in members[1:]
            )
            >= 0.65
        )
        rows = [row for row in feedback if row["user_index"] // 5 == cluster_index]
        positives = Counter(row["dish_id"] for row in rows if row["rating"] >= 4)
        assert sum(count >= 2 for count in positives.values()) >= 2
        assert cluster[0] == members[0]["cluster"]
