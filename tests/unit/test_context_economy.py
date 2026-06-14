"""Context economy: compression saves context without losing originals."""

from __future__ import annotations

from midas.core.context import ContextBudget, SafeContextCompressor


def test_compression_keeps_original_retrievable() -> None:
    text = "invoice chasing pain. " * 800
    compressor = SafeContextCompressor(ContextBudget(max_chars_per_chunk=1_200))
    chunk = compressor.compress("research-log", text)
    assert chunk.compressed is True
    assert chunk.saved_chars > 0
    assert compressor.retrieve_original(chunk.original_hash) == text
    assert chunk.original_hash in chunk.text


def test_proof_critical_context_is_not_compressed() -> None:
    text = "source quote " * 500
    compressor = SafeContextCompressor(ContextBudget(max_chars_per_chunk=800))
    chunk = compressor.compress("proof", text, proof_critical=True)
    assert chunk.compressed is False
    assert chunk.text == text
