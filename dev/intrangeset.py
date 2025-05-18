from typing import List, Tuple, Union as TypingUnion, ClassVar


class IntRangeSet:
    # Invariant: A list of sorted tuples (start, end) where start <= end,
    # and for any two adjacent ranges (s1, e1), (s2, e2), we have e1 < s2 - 1.
    ranges: List[Tuple[int, int]]

    empty: ClassVar["IntRangeSet"]  # type: ignore

    def __init__(self, values: List[TypingUnion[int, Tuple[int, int]]]):
        """
        Initializes an IntRangeSet from a list of integers or (start, end) tuples.
        The ranges are automatically sorted, merged, and validated.
        """
        processed_ranges = []
        for value in values:
            if isinstance(value, int):
                processed_ranges.append((value, value))
            elif isinstance(value, tuple) and len(value) == 2:
                start, end = value
                if not isinstance(start, int) or not isinstance(end, int):
                    raise TypeError(f"Range endpoints must be integers: {value}")
                if start > end:
                    raise ValueError(
                        f"Invalid range: start ({start}) cannot be greater than end ({end}) in {value}"
                    )
                processed_ranges.append(value)
            else:
                raise TypeError(
                    f"Invalid value type: {value}. Must be int or tuple[int, int]."
                )

        # Sort ranges primarily by start, secondarily by end for merging logic
        processed_ranges.sort()

        merged_ranges: List[Tuple[int, int]] = []
        for start, end in processed_ranges:
            if not merged_ranges:
                merged_ranges.append((start, end))
            else:
                last_start, last_end = merged_ranges[-1]
                # Merge if the current range overlaps or touches the last one (start <= last_end + 1)
                if start <= last_end + 1:
                    # Update the end of the last range if the current range extends further
                    merged_ranges[-1] = (last_start, max(last_end, end))
                else:
                    # Otherwise, add the new range as it's distinct
                    merged_ranges.append((start, end))

        self.ranges = merged_ranges
        # The invariant should now hold due to the sorting and merging logic.

    def union(self, other: "IntRangeSet") -> "IntRangeSet":
        """
        Returns a new IntRangeSet that is the union of this and another IntRangeSet.
        This method directly merges the ranges, preserving the invariant.
        """
        merged_ranges: List[Tuple[int, int]] = []
        i = 0  # Pointer for self.ranges
        j = 0  # Pointer for other.ranges

        # Iterate while there are ranges in either list
        while i < len(self.ranges) or j < len(other.ranges):
            # Determine the next range to consider (one with the smaller start)
            if i < len(self.ranges) and (
                j == len(other.ranges) or self.ranges[i][0] <= other.ranges[j][0]
            ):
                # Next range is from self
                current_start, current_end = self.ranges[i]
                i += 1
            elif j < len(other.ranges):
                # Next range is from other
                current_start, current_end = other.ranges[j]
                j += 1
            else:
                # Should not be reached if loop condition is correct
                break

            # Now, merge this 'current' range with the last one in merged_ranges if necessary
            if not merged_ranges:
                # If merged_ranges is empty, just add the first range
                merged_ranges.append((current_start, current_end))
            else:
                last_start, last_end = merged_ranges[-1]
                # Check for overlap or touching (current starts before or at last_end + 1)
                if current_start <= last_end + 1:
                    # Merge: Update the end of the last range in merged_ranges
                    merged_ranges[-1] = (last_start, max(last_end, current_end))
                else:
                    # No overlap: Add the current range as a new distinct range
                    merged_ranges.append((current_start, current_end))

        # Create a new instance and directly assign the correctly merged ranges
        # This bypasses the __init__'s merging logic, which is desirable here
        # as we've already done the work correctly.
        new_set = IntRangeSet([])  # Create an empty set instance
        new_set.ranges = merged_ranges  # Directly assign the calculated ranges
        return new_set

    def __add__(self, other: "IntRangeSet") -> "IntRangeSet":
        """
        Returns a new IntRangeSet that is the union of this and another IntRangeSet.
        Overloads the '+' operator.
        """
        if not isinstance(other, IntRangeSet):
            return NotImplemented
        return self.union(other)  # Calls the corrected union method

    def intersection(self, other: "IntRangeSet") -> "IntRangeSet":
        """Return a new ``IntRangeSet`` with values present in both sets."""
        result: List[Tuple[int, int]] = []
        i = 0
        j = 0

        while i < len(self.ranges) and j < len(other.ranges):
            s1, e1 = self.ranges[i]
            s2, e2 = other.ranges[j]

            start = max(s1, s2)
            end = min(e1, e2)
            if start <= end:
                result.append((start, end))

            if e1 < e2:
                i += 1
            else:
                j += 1

        new_set = IntRangeSet([])
        new_set.ranges = result
        return new_set

    def __and__(self, other: "IntRangeSet") -> "IntRangeSet":
        if not isinstance(other, IntRangeSet):
            return NotImplemented
        return self.intersection(other)

    def __contains__(self, value: int) -> bool:
        """Checks if an integer value is contained within any of the ranges."""
        if not isinstance(value, int):
            return False
        # TODO: Consider binary search for optimization if ranges are many
        # This requires ranges to be sorted, which they are by invariant.
        low, high = 0, len(self.ranges) - 1
        while low <= high:
            mid = (low + high) // 2
            start, end = self.ranges[mid]
            if start <= value <= end:
                return True
            elif value < start:
                high = mid - 1
            else:  # value > end
                low = mid + 1
        return False

    def __iter__(self):
        """Iterates over all individual integers contained in the ranges."""
        for start, end in self.ranges:
            # range() is efficient for this
            yield from range(start, end + 1)

    def __repr__(self) -> str:
        """Returns a developer-friendly string representation of the IntRangeSet."""
        # Create a more canonical representation usable with __init__
        range_strs = []
        for s, e in self.ranges:
            if s == e:
                range_strs.append(str(s))
            else:
                range_strs.append(f"({s}, {e})")
        return f"IntRangeSet([{', '.join(range_strs)}])"

    def __str__(self) -> str:
        """Returns a user-friendly string representation."""
        # Could be simplified, e.g., "{1-3, 5, 7-9}"
        range_strs = []
        for s, e in self.ranges:
            if s == e:
                range_strs.append(str(s))
            else:
                range_strs.append(f"{s}-{e}")  # Use hyphen for ranges
        return f"{{{', '.join(range_strs)}}}"

    def __eq__(self, other: object) -> bool:
        """Checks if two IntRangeSets are equal (contain the same ranges)."""
        if not isinstance(other, IntRangeSet):
            return NotImplemented
        return self.ranges == other.ranges

    def __hash__(self) -> int:
        """Returns a hash based on the ranges, making the set hashable."""
        return hash(tuple(self.ranges))  # ranges list -> tuple for hashing


# Initialize the class variable 'empty' after the class definition
IntRangeSet.empty = IntRangeSet([])

# # --- Example Usage (demonstrating the fix) ---
# set1 = IntRangeSet([(1, 3), (7, 9), 15]) # Ranges: [(1, 3), (7, 9), (15, 15)]
# set2 = IntRangeSet([(2, 4), 10, (14, 16)]) # Ranges: [(2, 4), (10, 10), (14, 16)]

# print(f"Set 1 (repr): {repr(set1)}")
# print(f"Set 1 (str): {str(set1)}")
# print(f"Set 2 (repr): {repr(set2)}")
# print(f"Set 2 (str): {str(set2)}")


# # Use the + operator (__add__ calls union)
# union_set_operator = set1 + set2
# print(f"Union (operator +) (repr): {repr(union_set_operator)}")
# # Expected: [(1, 4), (7, 10), (14, 16)]
# print(f"Union (operator +) (str): {str(union_set_operator)}")
# # Expected: {1-4, 7-10, 14-16}

# # Check containment (using binary search now)
# print(f"4 in union? {4 in union_set_operator}")  # True
# print(f"5 in union? {5 in union_set_operator}")  # False
# print(f"10 in union? {10 in union_set_operator}") # True
# print(f"14 in union? {14 in union_set_operator}") # True
# print(f"17 in union? {17 in union_set_operator}") # False

# # Check iteration
# print("Integers in union set:", list(union_set_operator))
# # Expected: [1, 2, 3, 4, 7, 8, 9, 10, 14, 15, 16]
