"""Choix des alias de joueurs (identifiants synthétiques)."""

from foot_predictor.mapping_builder.player_aliases import choose, to_yaml


def test_group_is_retained_when_ids_never_meet():
    fixtures = {1: {10, 11, 12}, 2: {20}}
    days = {1: {100, 101, 102}, 2: {200}}
    draft = choose([[2, 1]], fixtures, days)
    assert draft.aliases == {2: 1}  # principal : le plus de présences
    assert (draft.retained, draft.doubtful) == (1, 0)


def test_group_is_doubtful_when_ids_play_the_same_match_or_day():
    same_match = choose([[1, 2]], {1: {10}, 2: {10}}, {1: {100}, 2: {100}})
    same_day = choose([[1, 2]], {1: {10}, 2: {11}}, {1: {100}, 2: {100}})
    for draft in (same_match, same_day):
        assert draft.aliases == {} and draft.doubtful == 1


def test_tie_goes_to_the_smallest_id_and_ids_without_appearances():
    draft = choose([[7, 5, 9]], {5: {1}, 7: {2}}, {5: {1}, 7: {2}})
    assert draft.aliases == {7: 5, 9: 5}


def test_yaml_contains_only_numbers():
    text = to_yaml(choose([[2, 1]], {1: {1, 2}, 2: {3}}, {1: {1, 2}, 2: {3}}))
    body = text.split("\n\n", 1)[1]
    assert body == "aliases:\n  2: 1\n"
