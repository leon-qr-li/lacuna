"""SPIKE-ONLY workaround: rebuild a faster-whisper (CTranslate2) model from the
sherpa-onnx int8 ONNX export of Whisper large-v3 / large-v3-turbo.

Why: huggingface.co (Systran/faster-whisper-large-v3, mobiuslabsgmbh/faster-whisper-
large-v3-turbo, openai/whisper-*) and openaipublic.azureedge.net are blocked from the
spike container, but GitHub release assets (k2-fsa/sherpa-onnx) are reachable.
In production, download the official CT2 weights from Hugging Face instead.

Caveat (affects accuracy slightly, NOT a production path): the source weights are
onnxruntime dynamic-quantized (int8, per-tensor). We dequantize them to float and
CT2 re-quantizes to int8 at load time, so results include int8 quantization noise
on top of what the official faster-whisper int8 model would have.

Requires: onnx, numpy, ctranslate2, tokenizers, tiktoken, and the openai-whisper sdist
(for whisper/assets/multilingual.tiktoken and the LANGUAGES / alignment-head tables;
no torch needed).

Usage:
  python convert_sherpa_whisper_to_ct2.py --onnx-dir models/sherpa-onnx-whisper-turbo \
      --variant turbo --whisper-src dl_whisper/openai_whisper-20250625 --out models/ct2-turbo
"""
import argparse
import ast
import base64
import gzip
import json
import os
import re
from collections import defaultdict

import numpy as np
import onnx
from onnx import numpy_helper


def load(path):
    m = onnx.load(path)
    inits = {i.name: i for i in m.graph.initializer}
    cons = defaultdict(list)
    for n in m.graph.node:
        for i in n.input:
            cons[i].append(n)
    return m, inits, cons


def arr(inits, name):
    return numpy_helper.to_array(inits[name])


def deq_linear(inits, cons, node):
    """Return (W[out,in] float32, bias or None) for a MatMulInteger node."""
    wq = node.input[1]
    base = wq[: -len("_quantized")]
    q = arr(inits, wq).astype(np.int32)
    zp = arr(inits, base + "_zero_point").astype(np.int32)
    sc = arr(inits, base + "_scale").astype(np.float32)
    w = ((q - zp) * sc).astype(np.float32)  # [in, out]
    # follow Cast -> Mul -> Add(bias initializer)
    bias = None
    out = node.output[0]
    for _ in range(4):
        nxt = cons.get(out, [])
        if len(nxt) != 1:
            break
        n = nxt[0]
        if n.op_type == "Add":
            b = [i for i in n.input if i in inits]
            if b and inits[b[0]].dims == [w.shape[1]]:
                bias = arr(inits, b[0]).astype(np.float32)
            break
        if n.op_type not in ("Cast", "Mul"):
            break
        out = n.output[0]
    return np.ascontiguousarray(w.T), bias


def alignment_heads(b85: bytes, n_layers: int, n_heads: int):
    a = np.frombuffer(gzip.decompress(base64.b85decode(b85)), dtype=bool).reshape(n_layers, n_heads)
    return [(int(i), int(j)) for i, j in zip(*np.nonzero(a))]


def whisper_tables(src):
    init = open(os.path.join(src, "whisper", "__init__.py"), encoding="utf-8").read()
    heads = ast.literal_eval(re.search(r"_ALIGNMENT_HEADS = (\{.*?\n\})", init, re.S).group(1))
    tok = open(os.path.join(src, "whisper", "tokenizer.py"), encoding="utf-8").read()
    langs = ast.literal_eval(re.search(r"LANGUAGES = (\{.*?\n\})", tok, re.S).group(1))
    return heads, list(langs.keys())


def build_tokenizer(src, lang_codes):
    from tokenizers import Tokenizer, decoders, pre_tokenizers
    from tokenizers.models import BPE
    from transformers.convert_slow_tokenizer import TikTokenConverter

    conv = TikTokenConverter(vocab_file=os.path.join(src, "whisper", "assets", "multilingual.tiktoken"))
    vocab, merges = conv.extract_vocab_merges_from_model(conv.vocab_file)
    tk = Tokenizer(BPE(vocab, merges, fuse_unk=False))
    tk.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tk.decoder = decoders.ByteLevel()
    specials = (["<|endoftext|>", "<|startoftranscript|>"] + [f"<|{c}|>" for c in lang_codes[:100]]
                + ["<|translate|>", "<|transcribe|>", "<|startoflm|>", "<|startofprev|>", "<|nospeech|>",
                   "<|notimestamps|>"] + [f"<|{i * 0.02:.2f}|>" for i in range(1501)])
    from tokenizers import AddedToken
    tk.add_special_tokens([AddedToken(s, special=True, normalized=False) for s in specials])
    assert tk.get_vocab_size() == 51866, tk.get_vocab_size()
    assert tk.token_to_id("<|startoftranscript|>") == 50258 and tk.token_to_id("<|zh|>") == 50260
    assert tk.token_to_id("<|notimestamps|>") == 50364 and tk.token_to_id("<|0.00|>") == 50365
    return tk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx-dir", required=True)
    ap.add_argument("--variant", required=True, choices=["turbo", "large-v3"])
    ap.add_argument("--whisper-src", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    from ctranslate2.specs import common_spec, whisper_spec
    from ctranslate2.converters import utils

    v = a.variant
    em, ei, ec = load(os.path.join(a.onnx_dir, f"{v}-encoder.int8.onnx"))
    dm, di, dc = load(os.path.join(a.onnx_dir, f"{v}-decoder.int8.onnx"))
    meta = {p.key: p.value for p in em.metadata_props}
    n_enc, n_dec = int(meta["n_audio_layer"]), int(meta["n_text_layer"])
    h_enc, h_dec = int(meta["n_audio_head"]), int(meta["n_text_head"])
    spec = whisper_spec.WhisperSpec(n_enc, h_enc, n_dec, h_dec)

    def lin(w_b):
        s = common_spec.LinearSpec()
        s.weight = w_b[0]
        if w_b[1] is not None:
            s.bias = w_b[1]
        return s

    # ---------------- encoder ----------------
    convs = [n for n in em.graph.node if n.op_type == "Conv"]
    for cs, n in zip([spec.encoder.conv1, spec.encoder.conv2], convs):
        cs.weight = arr(ei, n.input[1]).astype(np.float32)
        cs.bias = arr(ei, n.input[2]).astype(np.float32)
    spec.encoder.position_encodings.encodings = arr(ei, "audioEncoder.positional_embedding").astype(np.float32)
    spec.encoder.layer_norm.gamma = arr(ei, "audioEncoder.ln_post.weight")
    spec.encoder.layer_norm.beta = arr(ei, "audioEncoder.ln_post.bias")
    mm = {n.name: n for n in em.graph.node if n.op_type == "MatMulInteger"}
    for i, L in enumerate(spec.encoder.layer):
        g = lambda k: deq_linear(ei, ec, mm[f"/audioEncoder/blocks.{i}/{k}/MatMul_quant"])
        q, k_, vv, o = lin(g("attn/query")), lin(g("attn/key")), lin(g("attn/value")), lin(g("attn/out"))
        assert k_.has_bias() is False and q.has_bias() and vv.has_bias() and o.has_bias(), f"enc bias map L{i}"
        utils.fuse_linear(L.self_attention.linear[0], [q, k_, vv])
        L.self_attention.linear[1].weight, L.self_attention.linear[1].bias = o.weight, o.bias
        L.self_attention.layer_norm.gamma = arr(ei, f"audioEncoder.blocks.{i}.attn_ln.weight")
        L.self_attention.layer_norm.beta = arr(ei, f"audioEncoder.blocks.{i}.attn_ln.bias")
        f0, f1 = g("mlp/mlp.0"), g("mlp/mlp.2")
        L.ffn.linear_0.weight, L.ffn.linear_0.bias = f0
        L.ffn.linear_1.weight, L.ffn.linear_1.bias = f1
        L.ffn.layer_norm.gamma = arr(ei, f"audioEncoder.blocks.{i}.mlp_ln.weight")
        L.ffn.layer_norm.beta = arr(ei, f"audioEncoder.blocks.{i}.mlp_ln.bias")

    # cross-attention K/V projections live in the encoder graph (key, value, key_1, value_1, ...)
    def sfx(i):
        return "" if i == 0 else f"_{i}"
    cross_kv = [(deq_linear(ei, ec, mm[f"/key{sfx(i)}/MatMul_quant"]),
                 deq_linear(ei, ec, mm[f"/value{sfx(i)}/MatMul_quant"])) for i in range(n_dec)]

    # ---------------- decoder ----------------
    dmm = [n for n in dm.graph.node if n.op_type == "MatMulInteger"]
    assert len(dmm) == 8 * n_dec, len(dmm)
    spec.decoder.embeddings.weight = arr(di, "textDecoder.token_embedding.weight").astype(np.float32)
    spec.decoder.position_encodings.encodings = arr(di, "textDecoder.positional_embedding").astype(np.float32)
    spec.decoder.layer_norm.gamma = arr(di, "textDecoder.ln.weight")
    spec.decoder.layer_norm.beta = arr(di, "textDecoder.ln.bias")
    for i, L in enumerate(spec.decoder.layer):
        nodes = dmm[8 * i: 8 * i + 8]
        kinds = [re.sub(r"_\d+$", "", n.name.split("/")[2 if "/mlp" in n.name else 1]) for n in nodes]
        assert kinds == ["query", "key", "value", "out", "query", "out", "mlp.0", "mlp.2"], (i, kinds)
        sq, sk, sv, so_, cq, co, f0, f1 = [deq_linear(di, dc, n) for n in nodes]
        utils.fuse_linear(L.self_attention.linear[0], [lin(sq), lin(sk), lin(sv)])
        L.self_attention.linear[1].weight, L.self_attention.linear[1].bias = so_
        L.self_attention.layer_norm.gamma = arr(di, f"textDecoder.blocks.{i}.attn_ln.weight")
        L.self_attention.layer_norm.beta = arr(di, f"textDecoder.blocks.{i}.attn_ln.bias")
        ck, cv = cross_kv[i]
        utils.fuse_linear(L.attention.linear[0], [lin(cq)])
        utils.fuse_linear(L.attention.linear[1], [lin(ck), lin(cv)])
        L.attention.linear[2].weight, L.attention.linear[2].bias = co
        L.attention.layer_norm.gamma = arr(di, f"textDecoder.blocks.{i}.cross_attn_ln.weight")
        L.attention.layer_norm.beta = arr(di, f"textDecoder.blocks.{i}.cross_attn_ln.bias")
        L.ffn.linear_0.weight, L.ffn.linear_0.bias = f0
        L.ffn.linear_1.weight, L.ffn.linear_1.bias = f1
        L.ffn.layer_norm.gamma = arr(di, f"textDecoder.blocks.{i}.mlp_ln.weight")
        L.ffn.layer_norm.beta = arr(di, f"textDecoder.blocks.{i}.mlp_ln.bias")
    spec.decoder.projection.weight = spec.decoder.embeddings.weight  # tied

    # ---------------- config / vocab ----------------
    heads_tab, lang_codes = whisper_tables(a.whisper_src)
    tk = build_tokenizer(a.whisper_src, lang_codes)
    vocab = [None] * tk.get_vocab_size()
    for t, i in tk.get_vocab(with_added_tokens=True).items():
        vocab[i] = t
    spec.register_vocabulary(vocab)
    non_speech = [int(x) for x in meta["non_speech_tokens"].split(",")]
    spec.config.suppress_ids = sorted(set(non_speech + [50258, 50359, 50360, 50361, 50362, 50363]))
    spec.config.suppress_ids_begin = [220, 50257]
    spec.config.lang_ids = list(range(50259, 50359))
    spec.config.alignment_heads = alignment_heads(heads_tab["large-v3-turbo" if v == "turbo" else "large-v3"],
                                                  n_dec, h_dec)
    spec.validate()
    spec.optimize(quantization="float16")
    os.makedirs(a.out, exist_ok=True)
    spec.save(a.out)
    tk.save(os.path.join(a.out, "tokenizer.json"))
    with open(os.path.join(a.out, "preprocessor_config.json"), "w") as f:
        json.dump({"feature_size": int(meta["n_mels"]), "sampling_rate": 16000, "hop_length": 160,
                   "chunk_length": 30, "n_fft": 400}, f)
    print("saved", a.out, "alignment_heads", spec.config.alignment_heads)


if __name__ == "__main__":
    main()
