"""Version label of the Model Compass scoring rules, recorded in every run artifact."""

# Release that last changed the scoring rules; set it to the next release with any change to scores or ranks.
METHODOLOGY_VERSION = "0.8.0"

MERGEABLE_COLLECTIONS: dict[str, frozenset[str]] = {"0.8.0": frozenset({"0.7.0"})}
"""Earlier versions whose pending files this version may merge, keyed by the current version.

Only for a release whose changes are all applied at merge to the stored raw
responses, so that collecting again would send the same requests and get the
same scores: 0.8.0 only widens where an exact answer is read (rescored at merge),
and accepts every answer 0.7.0 accepted. A release that changes a prompt, a
probe, a check run at collection or the catalog must not appear here.
"""


def can_merge(collected_version: object) -> bool:
    """Whether a pending file collected under *collected_version* can be merged by this version."""
    return collected_version == METHODOLOGY_VERSION or collected_version in MERGEABLE_COLLECTIONS.get(
        METHODOLOGY_VERSION, frozenset()
    )
