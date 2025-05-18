import pytest

from dev.intrangeset import IntRangeSet


def test_initialization_and_merging():
    s = IntRangeSet([1, (2, 2), (3, 4), (6, 8), 7])
    assert s.ranges == [(1, 4), (6, 8)]


def test_invalid_inputs():
    with pytest.raises(TypeError):
        IntRangeSet([1, "a"])
    with pytest.raises(ValueError):
        IntRangeSet([(5, 3)])
    with pytest.raises(TypeError):
        IntRangeSet([(1, 2, 3)])


def test_contains_and_iteration():
    s = IntRangeSet([(1, 3), 5, (7, 8)])
    assert 2 in s
    assert 4 not in s
    assert 5 in s
    assert list(s) == [1, 2, 3, 5, 7, 8]


def test_repr_and_str():
    s = IntRangeSet([1, (3, 4)])
    assert repr(s) == "IntRangeSet([1, (3, 4)])"
    assert str(s) == "{1, 3-4}"


def test_equality_and_hash():
    s1 = IntRangeSet([1, (3, 5)])
    s2 = IntRangeSet([(1, 1), (3, 5)])
    s3 = IntRangeSet([1, 4])
    assert s1 == s2
    assert hash(s1) == hash(s2)
    assert s1 != s3


def test_union():
    set1 = IntRangeSet([(1, 3), (7, 9), 15])
    set2 = IntRangeSet([(2, 4), 10, (14, 16)])
    expected = IntRangeSet([(1, 4), (7, 10), (14, 16)])
    assert set1.union(set2) == expected
    assert set2.union(set1) == expected
    assert (set1 + IntRangeSet.empty) == set1


def test_intersection():
    set1 = IntRangeSet([(1, 3), (7, 9), 15])
    set2 = IntRangeSet([(2, 4), 10, (14, 16)])
    expected = IntRangeSet([(2, 3), 15])
    assert set1.intersection(set2) == expected
    assert set2.intersection(set1) == expected
    assert (set1 & set2) == expected
    assert set1.intersection(IntRangeSet.empty) == IntRangeSet.empty
    disjoint = IntRangeSet([(20, 30)])
    assert set1.intersection(disjoint) == IntRangeSet.empty
