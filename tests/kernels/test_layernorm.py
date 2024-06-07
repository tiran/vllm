import pytest
import torch

from vllm.model_executor.layers.layernorm import RMSNorm
from vllm.utils import is_hpu

DTYPES = [torch.half, torch.bfloat16, torch.float]
NUM_TOKENS = [7, 83, 4096]  # Arbitrary values for testing
HIDDEN_SIZES = [768, 769, 770, 771, 5120, 5124, 5125, 5126, 8192,
                8199]  # Arbitrary values for testing
ADD_RESIDUAL = [False, True]
SEEDS = [0]
if is_hpu():
    DEVICES = ["hpu"]
else:
    DEVICES = [
        f"cuda:{i}" for i in range(1 if torch.cuda.device_count() == 1 else 2)
    ]


@pytest.mark.parametrize("num_tokens", NUM_TOKENS)
@pytest.mark.parametrize("hidden_size", HIDDEN_SIZES)
@pytest.mark.parametrize("add_residual", ADD_RESIDUAL)
@pytest.mark.parametrize("dtype", DTYPES)
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("device", DEVICES)
@torch.inference_mode()
def test_rms_norm(
    num_tokens: int,
    hidden_size: int,
    add_residual: bool,
    dtype: torch.dtype,
    seed: int,
    device: str,
) -> None:
    if is_hpu() and dtype == torch.half and add_residual:
        pytest.skip("Skipping test on HPU")
    torch.random.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
    elif is_hpu():
        torch.hpu.manual_seed(seed)
    torch.set_default_device(device)
    layer = RMSNorm(hidden_size).to(dtype=dtype)
    layer.weight.data.normal_(mean=1.0, std=0.1)
    scale = 1 / (2 * hidden_size)
    x = torch.randn(1, num_tokens, hidden_size, dtype=dtype, device=device)
    x *= scale
    residual = torch.randn_like(x) * scale if add_residual else None

    # NOTE(woosuk): The reference implementation should be executed first
    # because the custom kernel is in-place.
    ref_out = layer._forward(x, residual)
    out = layer(x, residual)
    # NOTE(woosuk): LayerNorm operators (including RMS) typically have larger
    # numerical errors than other operators because they involve reductions.
    # Therefore, we use a larger tolerance.
    if add_residual:
        assert torch.allclose(out[0], ref_out[0], atol=1e-2, rtol=1e-2)
        assert torch.allclose(out[1], ref_out[1], atol=1e-2, rtol=1e-2)
    else:
        assert torch.allclose(out, ref_out, atol=1e-2, rtol=1e-2)
