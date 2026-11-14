"""Train a small causal decoder with mHC. Educational FP32 implementation.

Python 3.12 / PyTorch 2.9.0 CPU. No tokenizer, dataset, or checkpoint downloads.
Run: python mhc_tiny_lm.py --steps 60 --output mhc-demo.pt
This implements mHC connections, not any released model/checkpoint layout.
"""
import argparse
import math
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F


def sinkhorn(logits, iterations=50):
    # Differentiable throughout; row/column normalization over stream axes.
    matrix = logits.softmax(dim=-1) + 1e-6
    for _ in range(iterations):
        matrix = matrix / matrix.sum(dim=-2, keepdim=True).clamp_min(1e-6)
        matrix = matrix / matrix.sum(dim=-1, keepdim=True).clamp_min(1e-6)
    return matrix


class MHC(nn.Module):
    def __init__(self, width, streams=4):
        super().__init__()
        assert streams >= 2
        self.n = streams
        self.proj = nn.Linear(streams * width, streams * streams + 2 * streams, bias=False)
        self.scale = nn.Parameter(torch.full((3,), 0.01))
        self.base = nn.Parameter(torch.zeros(streams * streams + 2 * streams))
        nn.init.xavier_uniform_(self.proj.weight)
        # Teaching initialization: read approximately the mean, write ~1,
        # and bias residual mixing towards its diagonal. Not a model recipe.
        with torch.no_grad():
            self.base[:streams].fill_(-math.log(streams - 1))
            self.base[2 * streams:].copy_((2 * torch.eye(streams)).flatten())

    def maps(self, x):
        # x: [B, T, n, C]. Normalize all n*C features for each token.
        flat = x.flatten(-2)
        normalized = flat * torch.rsqrt(flat.square().mean(-1, keepdim=True) + 1e-6)
        pre, post, res = self.proj(normalized).split([self.n, self.n, self.n * self.n], -1)
        bp, bq, br = self.base.split([self.n, self.n, self.n * self.n])
        p = torch.sigmoid(pre * self.scale[0] + bp)
        q = 2 * torch.sigmoid(post * self.scale[1] + bq)
        logits = (res * self.scale[2] + br).unflatten(-1, (self.n, self.n))
        return p, q, sinkhorn(logits)

    def forward(self, x, sublayer):
        p, q, r = self.maps(x)
        z = (p.unsqueeze(-1) * x).sum(dim=-2)  # [B, T, C]
        u = sublayer(z)                       # one Attention or FFN call
        mixed = r @ x                        # [B, T, n, C]
        return mixed + q.unsqueeze(-1) * u.unsqueeze(-2)


class CausalAttention(nn.Module):
    def __init__(self, width, heads=4):
        super().__init__()
        assert width % heads == 0
        self.heads = heads
        self.qkv = nn.Linear(width, 3 * width, bias=False)
        self.out = nn.Linear(width, width, bias=False)

    def forward(self, x):
        batch, length, width = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        q, k, v = [t.reshape(batch, length, self.heads, width // self.heads).transpose(1, 2)
                   for t in (q, k, v)]
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True, dropout_p=0.0)
        return self.out(y.transpose(1, 2).contiguous().reshape(batch, length, width))


class Block(nn.Module):
    def __init__(self, width, streams):
        super().__init__()
        self.attn_hc = MHC(width, streams)
        self.ffn_hc = MHC(width, streams)
        self.attn_branch = nn.Sequential(nn.RMSNorm(width), CausalAttention(width))
        self.ffn_branch = nn.Sequential(
            nn.RMSNorm(width), nn.Linear(width, 4 * width), nn.GELU(), nn.Linear(4 * width, width))

    def forward(self, x):
        x = self.attn_hc(x, self.attn_branch)
        x = self.ffn_hc(x, self.ffn_branch)
        return x


class TinyLM(nn.Module):
    def __init__(self, vocab=11, width=32, streams=4, layers=2, length=16):
        super().__init__()
        self.streams = streams
        self.token = nn.Embedding(vocab, width)
        self.position = nn.Embedding(length, width)
        self.blocks = nn.ModuleList([Block(width, streams) for _ in range(layers)])
        self.norm = nn.RMSNorm(width)
        self.head = nn.Linear(width, vocab, bias=False)

    def forward(self, ids):
        x = self.token(ids) + self.position(torch.arange(ids.shape[1], device=ids.device))
        x = x.unsqueeze(-2).expand(-1, -1, self.streams, -1)
        for block in self.blocks:
            x = block(x)
        return self.head(self.norm(x.mean(dim=-2)))


def batch(device, starts=None):
    # Predict the cyclic sequence 0,1,...,10,0,1,... from multiple starting phases.
    if starts is None:
        starts = torch.randint(11, (8, 1), device=device)
    ids = (starts + torch.arange(17, device=device)) % 11
    return ids[:, :-1], ids[:, 1:]


def loss_on(model, inputs, targets):
    return F.cross_entropy(model(inputs).flatten(0, 1), targets.flatten())


def connection_checks(model, inputs):
    errors, spreads = [], []
    handles = []

    def inspect(module, args, output):
        with torch.no_grad():
            p, q, r = module.maps(args[0])
            assert torch.isfinite(r).all() and (r >= 0).all()
            error = max((r.sum(-1) - 1).abs().max().item(), (r.sum(-2) - 1).abs().max().item())
            errors.append(error)
            spreads.append((output - output.mean(-2, keepdim=True)).abs().max().item())
            assert output.shape == args[0].shape

    for module in model.modules():
        if isinstance(module, MHC):
            handles.append(module.register_forward_hook(inspect))
    with torch.no_grad():
        logits = model(inputs)
    for handle in handles:
        handle.remove()
    assert max(errors) < 1e-4, errors
    assert max(spreads) > 1e-6, 'All streams remained identical'
    # Future tokens must not affect earlier positions.
    changed = inputs.clone()
    changed[:, 8:] = (changed[:, 8:] + 3) % 11
    with torch.no_grad():
        torch.testing.assert_close(logits[:, :8], model(changed)[:, :8], rtol=0, atol=1e-6)
    return max(errors), max(spreads)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps', type=int, default=60)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--output', type=Path, default=Path('mhc-demo.pt'))
    args = parser.parse_args()
    if args.steps < 1:
        parser.error('--steps must be positive')
    if args.output.exists():
        parser.error(f'Refusing to overwrite {args.output}')
    torch.manual_seed(7)
    torch.set_num_threads(2)
    device = torch.device(args.device)
    config = dict(vocab=11, width=32, streams=4, layers=2, length=16)
    model = TinyLM(**config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=0.0)
    probe_x, probe_y = batch(device, torch.arange(11, device=device).unsqueeze(1))
    model.eval()
    with torch.no_grad():
        initial = loss_on(model, probe_x, probe_y).item()
    initial_maps = {name: p.detach().clone() for name, p in model.named_parameters()
                    if '.proj.weight' in name}
    max_map_grad = {name: 0.0 for name in initial_maps}
    for step in range(1, args.steps + 1):
        model.train()
        inputs, targets = batch(device)
        optimizer.zero_grad(set_to_none=True)
        loss = loss_on(model, inputs, targets)
        assert torch.isfinite(loss)
        loss.backward()
        for name, parameter in model.named_parameters():
            assert parameter.grad is not None and torch.isfinite(parameter.grad).all(), name
            if name in max_map_grad:
                max_map_grad[name] = max(max_map_grad[name], parameter.grad.norm().item())
        grad_norm = nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
        optimizer.step()
        if step == 1 or step % 20 == 0 or step == args.steps:
            print(f'step={step:02d} loss={loss.item():.6f} grad_norm={grad_norm.item():.6f}')
    model.eval()
    with torch.no_grad():
        final = loss_on(model, probe_x, probe_y).item()
        reference = model(probe_x)
    assert all(v > 0 for v in max_map_grad.values()), max_map_grad
    parameters = dict(model.named_parameters())
    assert all(not torch.equal(old, parameters[name]) for name, old in initial_maps.items())
    error, spread = connection_checks(model, probe_x)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({'config': config, 'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
                'step': args.steps, 'rng_state': torch.get_rng_state()}, args.output)
    checkpoint = torch.load(args.output, map_location=device, weights_only=True)
    restored = TinyLM(**checkpoint['config']).to(device)
    restored.load_state_dict(checkpoint['model'])
    restored.eval()
    with torch.no_grad():
        torch.testing.assert_close(reference, restored(probe_x), rtol=0, atol=0)
    print(f'probe_loss={initial:.6f} -> {final:.6f}')
    print(f'mhc_projection_grad_max={max_map_grad}')
    print(f'sinkhorn_max_error={error:.3e} stream_spread={spread:.6f}')
    print(f'PASS: finite gradients, mHC updates, causal mask, stream shapes, checkpoint reload: {args.output}')
    print(f'Python/PyTorch runtime: torch={torch.__version__}, device={device}, dtype=float32')


if __name__ == '__main__':
    main()
