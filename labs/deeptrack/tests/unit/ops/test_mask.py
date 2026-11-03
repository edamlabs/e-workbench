"""CUITs never leave the process: bare, hyphenated, nested."""

from ops.mask import LIMIT, MASK, mask_clip, mask_data


def test_mask_nested() -> None:
    masked = mask_data(data={"a": ["CUIT 20-11111111-2", 7], "b": "27222222223"})
    assert masked == {"a": [f"CUIT {MASK}", 7], "b": MASK}


def test_mask_clip_limit() -> None:
    assert len(mask_clip("x" * (LIMIT * 2))) == LIMIT
