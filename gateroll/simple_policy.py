"""Ordinary same-information closed-step policy for the frozen static language.

This is a comparison, not a novel scheduling algorithm. The full certificate
contract still requires exact frontier construction and a minimum blocker;
those shared costs are retained rather than donated to this policy for free.
"""
from .model import LOCAL_ATOMS, O, N, Manifest, is_closed
from .planner import exact_frontier, minimum_blocking_witness


def schedule(manifest: Manifest) -> list[list[int]] | None:
    # Every required local mode is crossed in a complete one-role rollout.
    if any(not getattr(service, atom) for service in manifest.services
           for atom in LOCAL_ATOMS if atom != 'migrate' or service.stateful):
        return None
    state = [O] * len(manifest.services)
    path = [state[:]]
    for _ in range(2 * len(state)):
        for position, mode in enumerate(state):
            if mode == N:
                continue
            candidate = state[:]
            candidate[position] += 1
            if is_closed(manifest, tuple(candidate)):
                state = candidate
                path.append(state[:])
                break
        else:
            return None
    return path


def certificate(manifest: Manifest) -> dict:
    # Same declared inputs AND same full output/checker contract as reference.
    frontier = exact_frontier(manifest)
    path = schedule(manifest)
    admitted = path is not None
    if admitted != ((O,) * len(manifest.services) in frontier):
        raise ValueError('closed-step schedule disagrees with exact frontier')
    return {'case_id': manifest.case_id, 'family': manifest.family,
            'pair': manifest.pair, 'topology': manifest.topology,
            'services': list(manifest.names), 'admitted': admitted,
            'frontier': [list(state) for state in sorted(frontier)],
            'schedule': [] if path is None else path,
            'witness': [] if admitted else list(minimum_blocking_witness(manifest))}
