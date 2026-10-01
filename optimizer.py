"""Exakte, ausgewogene Zuordnung von Wikingern zu Gilden."""

from dataclasses import dataclass
import secrets


@dataclass(frozen=True)
class AssignmentResult:
    assignment: tuple[int, ...]
    score: int
    maximum_score: int
    optimal_solution_count: int


def optimize(
    preferences: list[list[int | None]],
    guild_count: int,
    minimum_sizes: list[int] | None = None,
    maximum_sizes: list[int] | None = None,
) -> AssignmentResult:
    """Maximiere Ranglistenpunkte unter Einhaltung der vorgegebenen Gildengrößen.

    Gildenindizes belegen ausdrückliche Rangplätze. Alle ``None``-Positionen
    stehen gemeinsam für die nicht genannten, gleichwertigen Gilden. Diese
    teilen sich den besten der mit ``None`` belegten Rangplätze.
    """
    if guild_count < 1:
        raise ValueError("Es muss mindestens eine Gilde geben.")
    if not preferences:
        raise ValueError("Es muss mindestens einen Wikinger geben.")

    for ranking in preferences:
        if len(ranking) != guild_count:
            raise ValueError("Jede Rangliste muss einen Eintrag pro Gilde enthalten.")
        explicit = [value for value in ranking if value is not None]
        if any(type(value) is not int or not 0 <= value < guild_count for value in explicit):
            raise ValueError("Die Rangliste enthält eine ungültige Gilde.")
        if len(set(explicit)) != len(explicit):
            raise ValueError("Eine Gilde darf nicht mehrfach ausdrücklich genannt werden.")

    viking_count = len(preferences)
    if minimum_sizes is None:
        minimum_sizes = [viking_count // guild_count] * guild_count
    if maximum_sizes is None:
        maximum_sizes = [(viking_count + guild_count - 1) // guild_count] * guild_count
    if (len(minimum_sizes) != guild_count or len(maximum_sizes) != guild_count
            or any(type(size) is not int or size < 0 for size in minimum_sizes + maximum_sizes)
            or any(minimum > maximum for minimum, maximum in zip(minimum_sizes, maximum_sizes))
            or sum(minimum_sizes) > viking_count or sum(maximum_sizes) < viking_count):
        raise ValueError("Die vorgegebenen Gildengrößen sind nicht erfüllbar.")
    # Zustand -> (Punktzahl, Anzahl optimaler Pfade). Der letzte Gildenzähler ist
    # durch die Zahl der bereits verteilten Wikinger bestimmt und daher redundant.
    states: dict[tuple[int, ...], tuple[int, int]] = {(0,) * (guild_count - 1): (0, 1)}
    predecessors: list[
        dict[tuple[int, ...], list[tuple[tuple[int, ...], int, int]]]
    ] = []

    for index, ranking in enumerate(preferences):
        explicit = [guild for guild in ranking if guild is not None]
        points = {
            guild: guild_count - rank
            for rank, guild in enumerate(ranking)
            if guild is not None
        }
        equal_ranks = [rank for rank, guild in enumerate(ranking) if guild is None]
        tied_points = guild_count - min(equal_ranks) if equal_ranks else 0
        for guild in set(range(guild_count)) - set(explicit):
            points[guild] = tied_points
        next_states: dict[tuple[int, ...], tuple[int, int]] = {}
        chosen: dict[tuple[int, ...], list[tuple[tuple[int, ...], int, int]]] = {}
        for counts, (score, path_count) in states.items():
            last_count = index - sum(counts)
            all_counts = counts + (last_count,)
            for guild in range(guild_count):
                if all_counts[guild] >= maximum_sizes[guild]:
                    continue
                new_counts_list = list(counts)
                if guild < guild_count - 1:
                    new_counts_list[guild] += 1
                new_counts = tuple(new_counts_list)
                new_score = score + points[guild]
                previous = next_states.get(new_counts)
                if previous is None or new_score > previous[0]:
                    next_states[new_counts] = (new_score, path_count)
                    chosen[new_counts] = [(counts, guild, path_count)]
                elif new_score == previous[0]:
                    next_states[new_counts] = (previous[0], previous[1] + path_count)
                    chosen[new_counts].append((counts, guild, path_count))
        states = next_states
        predecessors.append(chosen)

    valid = []
    for counts, value in states.items():
        last_count = viking_count - sum(counts)
        if all(minimum_sizes[guild] <= count <= maximum_sizes[guild]
               for guild, count in enumerate(counts + (last_count,))):
            valid.append((value[0], counts, value[1]))

    best_score = max(item[0] for item in valid)
    best_states = [item for item in valid if item[0] == best_score]
    solution_count = sum(item[2] for item in best_states)
    def weighted_choice(items, weight_index):
        target = secrets.randbelow(sum(item[weight_index] for item in items))
        for item in items:
            target -= item[weight_index]
            if target < 0:
                return item
        raise RuntimeError("Interner Fehler bei der Zufallsauswahl.")

    _, state, _ = weighted_choice(best_states, 2)
    assignment = [0] * viking_count
    for index in range(viking_count - 1, -1, -1):
        previous_state, guild, _ = weighted_choice(predecessors[index][state], 2)
        assignment[index] = guild
        state = previous_state

    return AssignmentResult(
        assignment=tuple(assignment),
        score=best_score,
        maximum_score=viking_count * guild_count,
        optimal_solution_count=solution_count,
    )
