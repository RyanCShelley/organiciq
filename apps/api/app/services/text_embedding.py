"""Text-only MiniLM inference, without image-processing dependencies.

Uses the same Qdrant ONNX weights, tokenizer, masked mean pooling and L2
normalization as the previous FastEmbed MiniLM path. Pin the model revision
so deployments never silently change page-matching vectors.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from collections.abc import Iterable, Iterator

import numpy as np
from huggingface_hub import snapshot_download
from tokenizers import AddedToken, Tokenizer
import onnxruntime as ort

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REPOSITORY = "Qdrant/all-MiniLM-L6-v2-onnx"
MODEL_REVISION = "d13954661f83248295ba75c1ed411eef3b7b936e"
MODEL_FILES = ["model.onnx", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"]


def download_model() -> Path:
    return Path(snapshot_download(
        MODEL_REPOSITORY, revision=MODEL_REVISION,
        cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"), allow_patterns=MODEL_FILES,
    ))


def pool_and_normalize(tokens: np.ndarray, mask: np.ndarray) -> np.ndarray:
    # Accumulate in float64, normalize before casting, matching FastEmbed.
    summed = np.sum(tokens, axis=1, where=mask[:, :, None].astype(bool), dtype=np.float64)
    pooled = summed / np.maximum(mask.sum(axis=1, keepdims=True), 1e-9)
    return (pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)).astype(tokens.dtype)


class TextEmbedding:
    def __init__(self, model_name: str = MODEL_NAME, *, model_dir: Path | None = None):
        if model_name != MODEL_NAME:
            raise ValueError("Only the calibrated MiniLM text model is supported")
        directory = model_dir if model_dir is not None else download_model()
        config = json.loads((directory / "tokenizer_config.json").read_text())
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256, direction="right")
        for token in json.loads((directory / "special_tokens_map.json").read_text()).values():
            self.tokenizer.add_special_tokens([AddedToken(**token) if isinstance(token, dict) else token])
        self.tokenizer.enable_padding(
            direction="right", pad_id=0, pad_token=config["pad_token"], pad_type_id=0,
        )
        self.session = ort.InferenceSession(str(directory / "model.onnx"), providers=["CPUExecutionProvider"])
        self.input_names = {item.name for item in self.session.get_inputs()}

    def embed(self, texts: Iterable[str], batch_size: int = 256) -> Iterator[np.ndarray]:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        batch: list[str] = []
        for text in texts:
            batch.append(text)
            if len(batch) == batch_size:
                yield from self._batch(batch)
                batch = []
        if batch:
            yield from self._batch(batch)

    def _batch(self, texts: list[str]) -> np.ndarray:
        encoded = self.tokenizer.encode_batch(texts)
        ids = np.array([item.ids for item in encoded], dtype=np.int64)
        mask = np.array([item.attention_mask for item in encoded], dtype=np.int64)
        inputs = {"input_ids": ids}
        if "attention_mask" in self.input_names:
            inputs["attention_mask"] = mask
        if "token_type_ids" in self.input_names:
            inputs["token_type_ids"] = np.zeros_like(ids)
        output = self.session.run(None, inputs)[0]
        return pool_and_normalize(output, mask)


if __name__ == "__main__":
    download_model()
