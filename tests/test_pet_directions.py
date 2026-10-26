import pytest
from ui.sprite_renderer import SpriteRenderer


@pytest.mark.parametrize("dx,dy,expected", [(0,-100,0), (100,-100,2), (100,0,4), (100,100,6), (0,100,8), (-100,100,10), (-100,0,12), (-100,-100,14)])
def test_source_direction_semantics(dx, dy, expected):
    assert SpriteRenderer.direction_index(dx, dy) == expected


def test_extended_atlas_and_bounded_direction_cache(qapp):
    app = qapp
    renderer = SpriteRenderer(scale=3)
    assert renderer._atlas.size().width() == 1536
    assert renderer._atlas.size().height() == 2288
    assert renderer._atlas.hasAlphaChannel()
    for x in range(-200, 201, 10):
        for y in range(-200, 201, 10):
            pix = renderer.look_at(x, y)
            assert pix.width() == 108
            assert pix.hasAlphaChannel()
    assert len(renderer._cache) <= 17
    assert renderer.look_at(0, -100).toImage() != renderer.look_at(0, 100).toImage()
    app.processEvents()
