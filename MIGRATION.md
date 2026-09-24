# CodeFormer — Modernization Report

Upstream: `sczhou/CodeFormer` @ `master`
Target runtime: **Python 3.10 – 3.13 · PyTorch ≥ 2.2 · TorchVision ≥ 0.17 · NumPy 1.26 – 2.x · SciPy ≥ 1.11**
Original runtime assumption: Python 3.8 · PyTorch 1.7.1 – 1.11 · NumPy 1.x · SciPy 1.9

Changes: **31 files · +182 / −86 lines.** No model architecture, layer definition, tensor shape, or numerical operation was altered. Pretrained checkpoints load unchanged.

---

## 1. Severity classification

| # | Issue | Fails on | Severity |
|---|---|---|---|
| 1 | `from distutils.version import LooseVersion` | Python 3.12+ without `setuptools` | **Hard break** |
| 2 | `gr.inputs.*` / `gr.outputs.*` / `queue(concurrency_count=)` | Gradio ≥ 4.0 | **Hard break** |
| 3 | `torch.load()` without `weights_only=` | PyTorch ≥ 2.6 | **Hard break** |
| 4 | `basicsr/setup.py` → `from utils.misc import …` | Always (broken import path) | **Hard break** |
| 5 | `from basicsr.version import __version__` | Any source checkout (file is git-ignored) | **Hard break** |
| 6 | `scipy.ndimage.filters` / `scipy.ndimage.interpolation` | SciPy 2.0 (deprecated since 1.10) | Deprecation → break |
| 7 | `pretrained=True/False` in TorchVision models | Deprecated since 0.13 | Deprecation → break |
| 8 | `torch.meshgrid` without `indexing=` | Warns since 1.10; error planned | Deprecation → break |
| 9 | `autograd.Variable(...)` | Legacy since 0.4 | Deprecation |
| 10 | `tb-nightly`, `future`, unpinned deps | Non-reproducible builds | Supply chain |

---

## 2. Hard breaks — what changed

### 2.1 `distutils` removal (PEP 632)

`distutils` was deleted from the standard library in Python 3.12. It appears to still work only because `setuptools` installs a shim — and since Python 3.12, `python -m venv` no longer installs `setuptools` by default. Verified on this machine:

```
$ python3 -c "import distutils; print(distutils.__file__)"
/usr/lib/python3/dist-packages/setuptools/_distutils/__init__.py   # shim only

$ python3 -S -c "import distutils"
ModuleNotFoundError: No module named 'distutils'
```

New file `basicsr/utils/version_util.py` provides `version_ge()`, which prefers `packaging.version.parse` and falls back to a dependency-free numeric tuple comparison. `basicsr/archs/arch_util.py` now calls it in the `DCNv2Pack` dispatch.

Behaviour parity was checked against the cases that matter for the TorchVision ≥ 0.9 branch, including PyPI local-version suffixes (`0.20.0+cu121`), which `LooseVersion` mishandled.

### 2.2 `torch.load` default flip

PyTorch 2.6 changed the default of `weights_only` from `False` to `True`. Every one of the 26 call sites in this repository relied on the old default and would raise `UnpicklingError` or a `WeightsUnpickler` error on load. All sites are now explicit, split by what the file actually contains:

1. **`weights_only=True`** (23 sites) — pure tensor state dicts: `codeformer.pth`, `vqgan_*.pth`, VGG features, RealESRGAN, RetinaFace, YOLOv5-face, face parsing, and all `['params_ema']` / `['params']` / `['params_d']` extractions. This is strictly safer than the original behaviour.
2. **`weights_only=False`** (3 sites) — files that legitimately carry pickled Python objects: `basicsr/train.py` resume state (optimizer/scheduler objects), `extract_ckpt.py` (a full pickled YOLOv5 `model`), and the auxiliary `.pth` dicts in the FFHQ blind datasets (component/latent/motion-kernel dicts).

`map_location=lambda storage, loc: storage` was also replaced with `map_location='cpu'` — identical semantics, and it survives pickling under `spawn`-based multiprocessing, which a lambda does not.

### 2.3 Gradio 4/5 API

`gr.inputs` and `gr.outputs` were removed outright in Gradio 4. `web-demos/hugging_face/app.py` now uses top-level components (`gr.Image`, `gr.Checkbox`, `gr.Number`, `gr.File`), `default=` was renamed to `value=`, and `queue(concurrency_count=2)` became `queue(default_concurrency_limit=2)`.

### 2.4 Packaging correctness

1. `basicsr/setup.py` imported `from utils.misc import gpu_is_available` — a path that never resolves from the repository root. Corrected to `basicsr.utils.misc`.
2. The same file imported `torch.utils.cpp_extension` at module scope, making the build impossible before torch is installed. Now wrapped in a guarded import with a `TORCH_AVAILABLE` flag.
3. `basicsr/__init__.py` imports `.version`, which only exists after `setup.py` runs — and `version.py` is git-ignored, so `import basicsr` failed in every fresh clone. A static `basicsr/version.py` is now committed, and `basicsr/utils/logger.py` guards the import.

---

## 3. Deprecations resolved

1. **SciPy namespaces.** `scipy.ndimage.filters` → `scipy.ndimage.gaussian_filter`; `scipy.ndimage.interpolation` → `scipy.ndimage.shift`. Both legacy namespaces are scheduled for removal in SciPy 2.0 and already emit `DeprecationWarning` on 1.17.
2. **TorchVision weights API.** `pretrained=False` → `weights=None`; `pretrained=True` → `weights='DEFAULT'`. Affects `basicsr/archs/vgg_arch.py` and `facelib/detection/retinaface/retinaface.py`. The `'DEFAULT'` string form avoids hard-coding an enum name, so it stays valid as TorchVision rotates weight versions.
3. **`torch.meshgrid` indexing.** Made `indexing='ij'` explicit in `basicsr/archs/arch_util.py` (optical-flow grid) and `facelib/.../models/yolo.py` (anchor grid). `'ij'` is the pre-1.10 default, so output is unchanged; the warning is gone and the code is immune to a future default flip.
4. **`autograd.Variable`.** Replaced with `.requires_grad_(True)` in the WGAN-GP gradient penalty.

---

## 4. Dependency set

`requirements.txt` was rewritten with lower bounds rather than bare names, plus three substantive changes:

| Removed | Reason | Replacement |
|---|---|---|
| `future` | Python 2 compatibility shim | deleted |
| `tb-nightly` | Unpinned nightly build; the original Replicate config froze `2.11.0a20220906` | `tensorboard>=2.16.0` |
| `opencv-python` | Pulls GUI libs; fails on headless servers without `libGL` | `opencv-python-headless>=4.9.0.80` |

Added: `packaging>=23.2` (for `version_util`), explicit `numpy>=1.26,<3`, `addict`, and torch/torchvision floors that match the `weights_only` and `weights=` APIs actually used.

`pyproject.toml` was added with PEP 621 metadata, `requires-python = ">=3.10"`, and two extras: `[train]` (tensorboard, yapf) and `[demo]` (gradio).

`web-demos/replicate/cog.yaml` moved from CUDA 11.3 / Python 3.8 / Torch 1.11 to CUDA 12.1 / Python 3.11 / Torch 2.4.

---

## 5. Verification performed

1. **Syntax.** All 90 `.py` files compile under Python 3.12.3 via `compileall`.
2. **Residual scan.** Zero remaining occurrences of `distutils`, `scipy.ndimage.filters`, `scipy.ndimage.interpolation`, `pretrained=`, `gr.inputs`, `gr.outputs`, `concurrency_count`, `autograd.Variable`, bare `torch.load(`, or un-indexed `torch.meshgrid`.
3. **Runtime spot-checks** on NumPy 2.4.4 / SciPy 1.17.1: `gaussian_filter` and `shift` replacements produce the expected outputs; `version_ge` matches `LooseVersion` semantics across five cases including a CUDA local-version suffix.

**Not verified (at the time):** end-to-end inference. See §8 — now verified. This container has no GPU and no PyTorch installed (the PyPI `torch` wheel pulls several GB of CUDA dependencies). Every change is static and behaviour-preserving, but you should run `python inference_codeformer.py -w 0.7 --input_path inputs/whole_imgs` on a real machine before trusting it in production.

---

## 6. Deliberately not changed

1. **Custom CUDA ops** (`basicsr/ops/dcn`, `fused_act`, `upfirdn2d`). These still compile against modern PyTorch, and the deformable-conv path already falls through to `torchvision.ops.deform_conv2d`. Removing them would be a larger, riskier refactor.
2. **`.pth` → `safetensors`.** Would be the right long-term move for the `weights_only=False` sites, but it invalidates every published checkpoint URL.
3. **Vendored `basicsr` fork.** Upstream `basicsr` has diverged; CodeFormer's copy carries project-specific architectures. Keeping the fork is correct.
4. **`np.hstack(...).astype(np.float32, copy=False)`** in `retinaface.py`. NumPy 2 changed `np.array(copy=False)` semantics, not `ndarray.astype(copy=False)`. This line is fine.
5. **Numerical behaviour.** No change to any loss, schedule, normalization, or architecture.

---

## 7. Applying this

```bash
git clone https://github.com/sczhou/CodeFormer.git
cd CodeFormer
git apply /path/to/codeformer-py312.patch

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # or: pip install -e .
python scripts/download_pretrained_models.py facelib
python scripts/download_pretrained_models.py CodeFormer

python inference_codeformer.py -w 0.7 --input_path inputs/whole_imgs
```

---

## 8. Rebuild notes (September 2026)

The repository had been published with only its top-level files; `basicsr/`, `facelib/`, `scripts/`, `options/`, `inputs/`, `assets/`, `web-demos/` and `weights/` were missing, so every script failed on import. They were restored from upstream `sczhou/CodeFormer` @ `b33cc7d` and the modernization above was re-applied, with these differences and additions:

1. **`distutils` removed without a replacement helper.** `torchvision>=0.17` is the declared floor, so the `< 0.9` branch in `DCNv2Pack` was dead code; it now calls `torchvision.ops.deform_conv2d` directly. No `version_util.py` exists.
2. **`basicsr/version.py` committed and un-ignored.** The upstream `.gitignore` excluded `version.py`, which is why fresh clones could not `import basicsr`.
3. **Fragile torch version regex removed** in `basicsr/utils/misc.py` and `facelib/detection/yolov5face/face_detector.py`; it raised `IndexError` on nightly/dev version strings. Replaced with `True` (floor is torch 2.2).
4. **`@torch.jit.script` removed** from `swish` in `vqgan_arch.py` (deprecated in current PyTorch; numerically identical).
5. **Video pipeline rewritten** (`basicsr/utils/video_util.py`, `inference_codeformer.py`):
   1. Frames are streamed read → restore → write. Previously the whole video was held in RAM twice (a 1-minute 1080p clip is ~11 GB of raw frames).
   2. Audio is re-encoded to AAC. Stream copy failed for codecs MP4 cannot hold (PCM from `.mov`/`.avi`).
   3. Frame count falls back to duration × fps when the container omits `nb_frames` (`.mkv`, `.webm`).
   4. FPS parsed with `Fraction` instead of `eval()`.
   5. Runtime `pip.main` auto-install removed (does not exist in modern pip); `ffmpeg-python` added to dependencies; a missing ffmpeg binary exits non-zero with install commands.
   6. Output name bug fixed (`--suffix` produced `name_suffix.png.mp4`).
   7. Video mode no longer writes per-frame PNGs; the output is the `.mp4`.
6. **Input handling:** `.webp`/`.bmp` images and `.mkv`/`.webm` videos accepted; missing paths, out-of-range `-w`, and `--has_aligned` with video now give a clear argparse error; unreadable images are skipped instead of crashing the batch.
7. **Web UI** (`web-demos/hugging_face/app.py`) runs locally from any working directory, uses local example images, and writes a unique output file per request (previously every request overwrote `output/out.png`).
8. **`scripts/smoke_test.py`** added: one command that proves an install works.

### Verified end to end

Python 3.12.3 · PyTorch 2.14 (CPU) · TorchVision 0.29 · NumPy 2.5.3 · SciPy 1.18.1 · OpenCV 5.0:

1. Whole-image restoration (4 faces detected), with and without `--bg_upsampler realesrgan --face_upsample`.
2. Video: `.mov` with PCM audio → `.mp4` (H.264 + AAC), all frames; `.mkv` frame-count fallback.
3. Colorization, inpainting, and `--has_aligned` restoration.
4. Detectors `retinaface_resnet50`, `retinaface_mobile0.25`, `YOLOv5n`.
5. Web UI launched from outside the repo and served a full request.
6. Fresh clone → install → `scripts/smoke_test.py` passes.
