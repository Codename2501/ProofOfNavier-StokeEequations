# Chapter 06 — Energy Identity: M/E/S  
The Three-Stage Confinement Structure in OS Geometry

---

## 6.1. Introduction

This chapter develops the **energy identity** of OS Geometry, based on the
three generative quantities:

- **M(t,ℓ)** — local concentration  
- **E(t,λ)** — scale-wise enstrophy  
- **S(T)** — temporal accumulation  

These quantities form the backbone of the **three-stage confinement structure**,  
which restricts where and how a Navier–Stokes blow-up can occur.

---

## 6.2. Definition of the OS Energy Quantities

### 6.2.1. Local Concentration M(t,ℓ)

$$ M(t,\ell) = \sup_{x_0\in\mathbb{R}^3} \frac{1}{\ell^3} \int_{B(x_0,\ell)} |\omega(t,x)|^2\,dx. $$

**Interpretation.**  
Measures how much vorticity energy is concentrated in a ball of radius ℓ.  
The **first danger indicator**.

---

### 6.2.2. Scale Energy E(t,λ)

$$ E(t,\lambda) = \lambda^2 \int_{\mathbb{R}^3} |\omega_\lambda(t,x)|^2\,dx. $$

**Interpretation.**  
Quantifies the **distribution of vorticity across scales**.  
Detects small-scale amplification.

---

### 6.2.3. Temporal Accumulation S(T)

$$ S(T) = \int_0^T \sup_{x_0\in\mathbb{R}^3} \int_{B(x_0,\sqrt{T-t})} |\nabla u(x,t)|^2\,dx\,dt. $$

**Interpretation.**  
Measures **how long** the system has remained in a high-energy state.  
The **time-direction filter**.

---

## 6.3. The Critical Scale ℓ₍c₎(t)

$$ \ell_c(t) = \inf\{\ell>0 : M(t,\ell)\ge M_c\}. $$

Below this scale, viscosity dominates;  
above it, nonlinearity may dominate.

---

## 6.4. The Three-Stage Confinement Structure

OS Geometry classifies blow-up using:

1. **M** — local concentration  
2. **E** — scale energy  
3. **S** — time accumulation  

Together, they **completely confine** blow-up.

---

## 6.5. The Three-Stage Inequalities

### Stage 1 — Local Concentration (M)

If  

$$ M(t,\ell) < M_c, $$

then **no blow-up can occur at scale ℓ**.

---

### Stage 2 — Scale Energy (E)

If  

$$ E(t,\lambda) < E_c, $$

then **no blow-up can occur at scale λ**.

---

### Stage 3 — Temporal Accumulation (S)

If  

$$ S(T) < S_c, $$

then **no blow-up can occur before time T**.

---

## 6.6. The OS Energy Identity

### Theorem 6.1 (OS Energy Identity)

For any smooth solution of OSG2ADV,

$$ \frac{d}{dt} M(t,\ell) + \frac{d}{dt} E(t,\lambda) + \frac{d}{dt} S(t) = \mathcal{D}_{\mathrm{OS}}(t) - \mathcal{N}_{\mathrm{OS}}(t), $$

where:

- $\mathcal{D}_{\mathrm{OS}}$: OS-dissipation (from OS-Laplacian)  
- $\mathcal{N}_{\mathrm{OS}}$: nonlinear transfer (stretching + advection)

This identity expresses the **full energy flow** in OS Geometry.

---

## 6.7. Confinement Principle

### Theorem 6.2 (Three-Stage Confinement)

A finite-time blow-up is possible **only if**:

$$ M(t,\ell)\ge M_c,\qquad E(t,\lambda)\ge E_c,\qquad S(t)\ge S_c $$

**all hold simultaneously** at the same point, scale, and time.

Otherwise, blow-up is **structurally impossible**.

---

## 6.8. Summary

This chapter established:

- Definitions of **M**, **E**, **S**  
- The critical scale **$\ell_c(t)$**  
- The three-stage inequalities  
- The OS energy identity  
- The confinement theorem  

These results form the analytic backbone of OS Geometry and prepare the ground for  
**Chapter 07: OSG2ADV**, the generative Navier–Stokes equation.