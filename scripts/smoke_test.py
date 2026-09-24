"""One-command check that the install works end to end.

    python scripts/smoke_test.py

Restores a bundled sample photo (downloads ~550 MB of model weights on first run)
and checks that an upscaled result was written. Exit code 0 = working.
"""
import os
import subprocess
import sys
import tempfile

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, 'inputs', 'whole_imgs', '04.jpg')

with tempfile.TemporaryDirectory() as out:
    cmd = [sys.executable, 'inference_codeformer.py', '-w', '0.7', '-i', SAMPLE, '-o', out]
    subprocess.run(cmd, cwd=ROOT, check=True)
    result = os.path.join(out, 'final_results', '04.png')
    src, dst = cv2.imread(SAMPLE), cv2.imread(result)
    assert dst is not None, f'No output written to {result}'
    assert dst.shape[0] > src.shape[0] and dst.shape[1] > src.shape[1], 'Output is not larger than input'
    print(f'\nOK: {src.shape[1]}x{src.shape[0]} -> {dst.shape[1]}x{dst.shape[0]}. Your install works.')
