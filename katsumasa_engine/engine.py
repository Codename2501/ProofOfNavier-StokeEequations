"""
engine.py

Global Regularity of the 3D Navier–Stokes Equations via OS Geometry
OSG2ADV vorticity engine (JAX implementation, periodic box [0, 2π]^3)

Author: Katsumasa Matsui

Note:
  This version forces JAX to run on CPU via:
      JAX_PLATFORM_NAME=cpu
  for stable, theory-focused runs.
"""

import os
os.environ["JAX_PLATFORM_NAME"] = "cpu"  # Force the use of the CPU backend

import math
from dataclasses import dataclass

import numpy as np
import jax
import jax.numpy as jnp
from jax import vmap

# ============================================================
# Configuration
# ============================================================

# Fix 1: Add frozen=True to make the dataclass hashable for JIT compilation
@dataclass(frozen=True)
class Config:
    N: int = 64                     # grid size per dimension
    L: float = 2.0 * math.pi        # domain length
    nu: float = 1e-3                # viscosity
    dt: float = 1e-3                # time step
    steps: int = 100000             # total steps (updated to 100,000)
    log_interval: int = 10000       # logging interval (updated to 10,000)
    alpha: float = 1.0              # OS-metric parameter
    eps: float = 1e-8               # regularization for |ω|
    seed: int = 0                   # RNG seed
    initial_condition: str = "kida_pelz"  # default condition; overridden in main loop


# ============================================================
# Grid and differential operators
# ============================================================

def make_grid(cfg: Config):
    N = cfg.N
    L = cfg.L
    dx = L / N
    # Generate on CPU first, then convert to JAX array (also useful to avoid Metal bugs)
    x = np.linspace(0.0, L - dx, N, dtype=np.float32)
    x = jnp.asarray(x)
    X, Y, Z = jnp.meshgrid(x, x, x, indexing="ij")
    return X, Y, Z, dx


def fftfreq(N, L):
    """Periodic wave numbers for FFT on [0, L]."""
    k = jnp.fft.fftfreq(N, d=L / (2.0 * math.pi * N))  # scaled so that k ~ integer
    return k


def make_k_vectors(cfg: Config):
    N = cfg.N
    L = cfg.L
    k = fftfreq(N, L)
    kx, ky, kz = jnp.meshgrid(k, k, k, indexing="ij")
    k2 = kx**2 + ky**2 + kz**2
    k2 = jnp.where(k2 == 0.0, 1.0, k2)  # avoid division by zero
    return kx, ky, kz, k2


# ============================================================
# Initial conditions (vorticity)
# ============================================================

def kida_pelz_vorticity(X, Y, Z):
    """
    Simple Kida–Pelz-like initial vorticity (not exact original, but representative).
    """
    s = 1.0
    wx = s * jnp.sin(X) * jnp.cos(Y) * jnp.cos(Z)
    wy = -s * jnp.cos(X) * jnp.sin(Y) * jnp.cos(Z)
    wz = 0.0 * X
    return jnp.stack([wx, wy, wz], axis=-1)


def kerr_vorticity(X, Y, Z):
    """
    Simple Kerr-type anti-parallel vortex tubes (schematic).
    """
    x0 = jnp.pi / 2.0
    y0 = jnp.pi / 2.0
    r1 = jnp.sqrt((X - x0)**2 + (Y - y0)**2)
    r2 = jnp.sqrt((X - (jnp.pi * 3.0 / 2.0))**2 + (Y - y0)**2)
    sigma = 0.3
    wx = jnp.exp(-r1**2 / sigma**2) - jnp.exp(-r2**2 / sigma**2)
    wy = 0.0 * X
    wz = 0.0 * X
    return jnp.stack([wx, wy, wz], axis=-1)


def hou_li_vorticity(X, Y, Z):
    """
    Hou–Li-type initial vorticity (simplified model).
    """
    a = 0.5
    wx = jnp.sin(X) * jnp.cos(Y) * jnp.cos(Z)
    wy = -jnp.cos(X) * jnp.sin(Y) * jnp.cos(Z)
    wz = a * jnp.sin(X) * jnp.sin(Y) * jnp.sin(Z)
    return jnp.stack([wx, wy, wz], axis=-1)


def make_initial_vorticity(cfg: Config, X, Y, Z):
    if cfg.initial_condition == "kida_pelz":
        return kida_pelz_vorticity(X, Y, Z)
    elif cfg.initial_condition == "kerr":
        return kerr_vorticity(X, Y, Z)
    elif cfg.initial_condition == "hou_li":
        return hou_li_vorticity(X, Y, Z)
    else:
        raise ValueError(f"Unknown initial condition: {cfg.initial_condition}")


# ============================================================
# Biot–Savart: ω → v (periodic, FFT-based)
# ============================================================

def vorticity_to_velocity(omega, cfg: Config, kx, ky, kz, k2):
    """
    Given vorticity ω(x), compute velocity v(x) via Biot–Savart in Fourier space:
        v̂(k) = i k × ω̂(k) / |k|^2
    """
    wx, wy, wz = omega[..., 0], omega[..., 1], omega[..., 2]
    wx_hat = jnp.fft.fftn(wx)
    wy_hat = jnp.fft.fftn(wy)
    wz_hat = jnp.fft.fftn(wz)

    # k × ω̂
    vx_hat = 1j * (ky * wz_hat - kz * wy_hat) / k2
    vy_hat = 1j * (kz * wx_hat - kx * wz_hat) / k2
    vz_hat = 1j * (kx * wy_hat - ky * wx_hat) / k2

    vx = jnp.fft.ifftn(vx_hat).real
    vy = jnp.fft.ifftn(vy_hat).real
    vz = jnp.fft.ifftn(vz_hat).real

    return jnp.stack([vx, vy, vz], axis=-1)


# ============================================================
# OS Geometry: metric, connection, OS-Laplacian
# ============================================================

def compute_os_metric(omega, cfg: Config):
    """
    Construct OS-metric g_ij and its inverse g^{ij} from vorticity direction.
    """
    alpha = cfg.alpha
    eps = cfg.eps

    # |ω|
    wnorm = jnp.linalg.norm(omega, axis=-1)
    wnorm_safe = wnorm + eps

    # unit direction
    w_hat = omega / wnorm_safe[..., None]

    # g^{ij} = (δ^{ij} + α |ω|^2 w^i w^j)
    w2 = wnorm**2
    delta = jnp.eye(3)

    def make_g_inv_at_point(wh, w2_scalar):
        return delta + alpha * w2_scalar * jnp.outer(wh, wh)

    g_inv = vmap(
        vmap(
            vmap(make_g_inv_at_point, in_axes=(0, 0)),
            in_axes=(0, 0)
        ),
        in_axes=(0, 0)
    )(w_hat, w2)

    # Invert to get g_ij
    def inv3(A):
        return jnp.linalg.inv(A)

    g = vmap(
        vmap(
            vmap(inv3, in_axes=0),
            in_axes=0
        ),
        in_axes=0
    )(g_inv)

    return g, g_inv


def gradient_scalar(f, dx):
    """
    Central difference gradient of scalar field f: ∇f
    """
    df_dx = (jnp.roll(f, -1, axis=0) - jnp.roll(f, 1, axis=0)) / (2.0 * dx)
    df_dy = (jnp.roll(f, -1, axis=1) - jnp.roll(f, 1, axis=1)) / (2.0 * dx)
    df_dz = (jnp.roll(f, -1, axis=2) - jnp.roll(f, 1, axis=2)) / (2.0 * dx)
    return jnp.stack([df_dx, df_dy, df_dz], axis=-1)


def gradient_vector(u, dx):
    """
    Gradient of vector field u: (∂_j u^i)
    Returns array shape (Nx, Ny, Nz, 3, 3) with indices (i, j).
    """
    ux, uy, uz = u[..., 0], u[..., 1], u[..., 2]
    gux = gradient_scalar(ux, dx)
    guy = gradient_scalar(uy, dx)
    guz = gradient_scalar(uz, dx)
    grad = jnp.stack([gux, guy, guz], axis=-2)  # (..., i, j)
    return grad


def compute_connection(g, g_inv, dx):
    """
    Compute Levi–Civita connection Γ^i_{jk} from metric g_ij.
    """
    g00 = g[..., 0, 0]
    g01 = g[..., 0, 1]
    g02 = g[..., 0, 2]
    g11 = g[..., 1, 1]
    g12 = g[..., 1, 2]
    g22 = g[..., 2, 2]

    dg00 = gradient_scalar(g00, dx)
    dg01 = gradient_scalar(g01, dx)
    dg02 = gradient_scalar(g02, dx)
    dg11 = gradient_scalar(g11, dx)
    dg12 = gradient_scalar(g12, dx)
    dg22 = gradient_scalar(g22, dx)

    def assemble_dg():
        dg = jnp.zeros(g.shape + (3,))
        dg = dg.at[..., 0, 0, :].set(dg00)
        dg = dg.at[..., 0, 1, :].set(dg01)
        dg = dg.at[..., 1, 0, :].set(dg01)
        dg = dg.at[..., 0, 2, :].set(dg02)
        dg = dg.at[..., 2, 0, :].set(dg02)
        dg = dg.at[..., 1, 1, :].set(dg11)
        dg = dg.at[..., 1, 2, :].set(dg12)
        dg = dg.at[..., 2, 1, :].set(dg12)
        dg = dg.at[..., 2, 2, :].set(dg22)
        return dg

    dg = assemble_dg()  # (..., i, j, k)

    def gamma_at_point(g_inv_ijk, dg_ijk):
        Gamma = jnp.zeros((3, 3, 3))
        for i in range(3):
            for j in range(3):
                for k in range(3):
                    s = 0.0
                    for m in range(3):
                        term = (
                            dg_ijk[m, k, j]
                            + dg_ijk[m, j, k]
                            - dg_ijk[j, k, m]
                        )
                        s = s + g_inv_ijk[i, m] * term
                    Gamma = Gamma.at[i, j, k].set(0.5 * s)
        return Gamma

    Gamma = vmap(
        vmap(
            vmap(gamma_at_point, in_axes=(0, 0)),
            in_axes=(0, 0)
        ),
        in_axes=(0, 0)
    )(g_inv, dg)

    return Gamma  # (..., i, j, k)


def os_laplacian_vector(u, g_inv, Gamma, dx):
    """
    OS-Laplacian of vector field u:
        (Δ_OS u)^i ≈ g^{jj} ∂_j ∂_j u^i
    """
    ux, uy, uz = u[..., 0], u[..., 1], u[..., 2]

    def lap_scalar(f):
        d2f_dx2 = (jnp.roll(f, -1, axis=0) - 2.0 * f + jnp.roll(f, 1, axis=0)) / (dx**2)
        d2f_dy2 = (jnp.roll(f, -1, axis=1) - 2.0 * f + jnp.roll(f, 1, axis=1)) / (dx**2)
        d2f_dz2 = (jnp.roll(f, -1, axis=2) - 2.0 * f + jnp.roll(f, 1, axis=2)) / (dx**2)
        return d2f_dx2, d2f_dy2, d2f_dz2

    uxx_x, uyy_x, uzz_x = lap_scalar(ux)
    uxx_y, uyy_y, uzz_y = lap_scalar(uy)
    uxx_z, uyy_z, uzz_z = lap_scalar(uz)

    gxx = g_inv[..., 0, 0]
    gyy = g_inv[..., 1, 1]
    gzz = g_inv[..., 2, 2]

    lap_x = gxx * uxx_x + gyy * uyy_x + gzz * uzz_x
    lap_y = gxx * uxx_y + gyy * uyy_y + gzz * uzz_y
    lap_z = gxx * uxx_z + gyy * uyy_z + gzz * uzz_z

    return jnp.stack([lap_x, lap_y, lap_z], axis=-1)


# ============================================================
# Vorticity equation: OSG2ADV
# ============================================================

def advective_term(omega, v, dx):
    """
    Compute -(v·∇)ω + (ω·∇)v
    """
    grad_omega = gradient_vector(omega, dx)  # (..., i, j)
    grad_v = gradient_vector(v, dx)

    def contract_v_grad_omega(grad_omega_ij, v_j):
        res = jnp.zeros(3)
        for i in range(3):
            s = 0.0
            for j in range(3):
                s = s + v_j[j] * grad_omega_ij[i, j]
            res = res.at[i].set(s)
        return res

    def contract_w_grad_v(grad_v_ij, w_j):
        res = jnp.zeros(3)
        for i in range(3):
            s = 0.0
            for j in range(3):
                s = s + w_j[j] * grad_v_ij[i, j]
            res = res.at[i].set(s)
        return res

    adv1 = vmap(
        vmap(
            vmap(contract_v_grad_omega, in_axes=(0, 0)),
            in_axes=(0, 0)
        ),
        in_axes=(0, 0)
    )(grad_omega, v)

    adv2 = vmap(
        vmap(
            vmap(contract_w_grad_v, in_axes=(0, 0)),
            in_axes=(0, 0)
        ),
        in_axes=(0, 0)
    )(grad_v, omega)

    return -adv1 + adv2


def rhs_omega(omega, cfg: Config, X, Y, Z, dx, kx, ky, kz, k2):
    """
    Right-hand side of OSG2ADV:
        ∂_t ω = -(v·∇)ω + (ω·∇)v + ν Δ_OS ω
    """
    v = vorticity_to_velocity(omega, cfg, kx, ky, kz, k2)
    g, g_inv = compute_os_metric(omega, cfg)
    Gamma = compute_connection(g, g_inv, dx)
    adv = advective_term(omega, v, dx)
    lap = os_laplacian_vector(omega, g_inv, Gamma, dx)
    return adv + cfg.nu * lap


# ============================================================
# Time stepping
# ============================================================

# Fix 2 & 3: Apply JIT compilation and use 2nd-order RK (Heun's method) for theoretical validation
@jax.jit(static_argnums=(1,))
def step_rk2(omega, cfg: Config, X, Y, Z, dx, kx, ky, kz, k2):
    """
    2nd-order Runge-Kutta (Heun's method) step for OSG2ADV.
    """
    # k1 = F(ω_n)
    k1 = rhs_omega(omega, cfg, X, Y, Z, dx, kx, ky, kz, k2)
    # Predictor: ω* = ω_n + dt * k1
    omega_pred = omega + cfg.dt * k1
    # k2 = F(ω*)
    k2_val = rhs_omega(omega_pred, cfg, X, Y, Z, dx, kx, ky, kz, k2)
    
    # Corrector: ω_{n+1} = ω_n + (dt/2) * (k1 + k2)
    return omega + (cfg.dt / 2.0) * (k1 + k2_val)


def max_vorticity(omega):
    return jnp.max(jnp.linalg.norm(omega, axis=-1))


# ============================================================
# Main simulation loop
# ============================================================

def run_simulation(cfg: Config):
    import time
    
    X, Y, Z, dx = make_grid(cfg)
    kx, ky, kz, k2 = make_k_vectors(cfg)

    omega = make_initial_vorticity(cfg, X, Y, Z)

    print(">> [READY] Starting singularity test (CPU mode)...")
    print(">> [IGNITION] OSG2ADV + OS Geometry Engine START! (JAX_PLATFORM_NAME=cpu)")
    print(f">> Initial condition: {cfg.initial_condition}")
    print(f">> Grid: N = {cfg.N}, dx = {dx:.6f}, ν = {cfg.nu}, dt = {cfg.dt}")

    start_time = time.time()

    for step in range(1, cfg.steps + 1):
        # Update using the modified RK2 scheme (JIT-compiled)
        omega = step_rk2(omega, cfg, X, Y, Z, dx, kx, ky, kz, k2)

        if step % cfg.log_interval == 0:
            M = float(max_vorticity(omega))
            print(f"Step {step:06d} | Max Vorticity (M): {M:.6f}")

    end_time = time.time()
    print(f">> Simulation finished in {end_time - start_time:.2f} seconds.")
    return omega


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    # List of initial conditions to test
    conditions = ["kida_pelz", "kerr", "hou_li"]
    
    for cond in conditions:
        print(f"\n{'='*60}")
        print(f"🚀 [EXPERIMENT START] Condition: {cond} / 100,000 Steps")
        print(f"{'='*60}")
        
        cfg = Config(
            N=64,
            L=2.0 * math.pi,
            nu=1e-3,
            dt=1e-3,
            steps=100000,          # Set to 100,000 steps
            log_interval=10000,    # Output every 10,000 steps
            alpha=1.0,
            eps=1e-8,
            seed=0,
            initial_condition=cond,  # Automatically set the condition from the list
        )
        
        # Run the simulation
        final_omega = run_simulation(cfg)
        
        # Since 100,000 steps is a long calculation, saving the final data automatically is recommended for safety
        filename = f"final_omega_100000steps_{cond}.npy"
        np.save(filename, np.asarray(final_omega))
        print(f">> [SAVED] Final result saved to {filename}.\n")