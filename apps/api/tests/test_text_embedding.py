import numpy as np
import pytest

from app.services.text_embedding import TextEmbedding, pool_and_normalize


def test_pooling_excludes_padding_and_normalizes():
    tokens = np.array([[[3, 0], [0, 4], [999, 999]]], dtype=np.float32)
    result = pool_and_normalize(tokens, np.array([[1, 1, 0]]))
    np.testing.assert_allclose(result, [[0.6, 0.8]], atol=1e-7)
    assert result.dtype == np.float32


def test_empty_mask_stays_finite():
    result = pool_and_normalize(np.ones((1, 2, 3), dtype=np.float32), np.zeros((1, 2), dtype=np.int64))
    np.testing.assert_array_equal(result, np.zeros((1, 3)))


def test_embedding_batches_without_losing_order():
    model = TextEmbedding.__new__(TextEmbedding)
    seen = []

    def batch(values):
        seen.append(list(values))
        return [np.array([int(value)]) for value in values]

    model._batch = batch
    assert [int(value[0]) for value in model.embed(map(str, range(5)), batch_size=2)] == list(range(5))
    assert seen == [['0', '1'], ['2', '3'], ['4']]
    assert list(model.embed([])) == []
    with pytest.raises(ValueError):
        list(model.embed(['x'], batch_size=0))


def test_rejects_uncalibrated_models_before_loading():
    with pytest.raises(ValueError):
        TextEmbedding('different/model')
